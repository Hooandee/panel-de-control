import ctypes as C
import errno
import fcntl
import mmap
import os
import select
import socket
from dataclasses import dataclass

LEASE_SOCKET = "/tmp/gamescope-lease.sock"

_CAP_UNIVERSAL_PLANES = 2
_CAP_ATOMIC = 3
_OBJECT_CRTC = 0xCCCCCCCC
_OBJECT_CONNECTOR = 0xC0C0C0C0
_OBJECT_PLANE = 0xEEEEEEEE
_PAGE_FLIP_EVENT = 0x1
_ATOMIC_NONBLOCK = 0x200
_ATOMIC_ALLOW_MODESET = 0x400
_IOCTL_CREATE_DUMB = 0xC02064B2
_IOCTL_MAP_DUMB = 0xC01064B3

_U32P = C.POINTER(C.c_uint32)


class _Resources(C.Structure):
    _fields_ = [
        ("count_fbs", C.c_int), ("fbs", _U32P),
        ("count_crtcs", C.c_int), ("crtcs", _U32P),
        ("count_connectors", C.c_int), ("connectors", _U32P),
        ("count_encoders", C.c_int), ("encoders", _U32P),
        ("limits", C.c_uint32 * 4),
    ]


class _PlaneResources(C.Structure):
    _fields_ = [("count_planes", C.c_uint32), ("planes", _U32P)]


class _Mode(C.Structure):
    _fields_ = [
        ("clock", C.c_uint32),
        ("timings", C.c_uint16 * 10),
        ("vrefresh", C.c_uint32), ("flags", C.c_uint32), ("type", C.c_uint32),
        ("name", C.c_char * 32),
    ]


class _Connector(C.Structure):
    _fields_ = [
        ("connector_id", C.c_uint32), ("encoder_id", C.c_uint32),
        ("connector_type", C.c_uint32), ("connector_type_id", C.c_uint32),
        ("connection", C.c_int), ("mm_width", C.c_uint32), ("mm_height", C.c_uint32),
        ("subpixel", C.c_int), ("count_modes", C.c_int), ("modes", C.POINTER(_Mode)),
    ]


class _Properties(C.Structure):
    _fields_ = [("count_props", C.c_uint32), ("props", _U32P), ("prop_values", C.POINTER(C.c_uint64))]


class _Property(C.Structure):
    _fields_ = [("prop_id", C.c_uint32), ("flags", C.c_uint32), ("name", C.c_char * 32)]


class _CreateDumb(C.Structure):
    _fields_ = [
        ("height", C.c_uint32), ("width", C.c_uint32), ("bpp", C.c_uint32), ("flags", C.c_uint32),
        ("handle", C.c_uint32), ("pitch", C.c_uint32), ("size", C.c_uint64),
    ]


class _MapDumb(C.Structure):
    _fields_ = [("handle", C.c_uint32), ("pad", C.c_uint32), ("offset", C.c_uint64)]


class LeaseError(RuntimeError):
    pass


def _libdrm():
    lib = C.CDLL("libdrm.so.2", use_errno=True)
    lib.drmModeGetResources.restype = C.POINTER(_Resources)
    lib.drmModeGetPlaneResources.restype = C.POINTER(_PlaneResources)
    lib.drmModeGetConnector.restype = C.POINTER(_Connector)
    lib.drmModeObjectGetProperties.restype = C.POINTER(_Properties)
    lib.drmModeGetProperty.restype = C.POINTER(_Property)
    lib.drmModeAtomicAlloc.restype = C.c_void_p
    lib.drmModeAtomicAddProperty.argtypes = [C.c_void_p, C.c_uint32, C.c_uint32, C.c_uint64]
    lib.drmModeAtomicCommit.argtypes = [C.c_int, C.c_void_p, C.c_uint32, C.c_void_p]
    lib.drmModeAtomicFree.argtypes = [C.c_void_p]
    return lib


def receive_lease(path: str = LEASE_SOCKET) -> tuple[socket.socket, int]:
    # Keep the socket open: gamescope leaves bottom-panel touch alone only while a lease client is connected.
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(path)
    _, ancillary, _, _ = sock.recvmsg(1, socket.CMSG_SPACE(4))
    for level, kind, data in ancillary:
        if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS and len(data) >= 4:
            return sock, int.from_bytes(data[:4], "little")
    sock.close()
    raise LeaseError("no_lease_fd")


@dataclass
class Buffer:
    fb_id: int
    pitch: int
    memory: mmap.mmap


class LeasedPanel:
    def __init__(self, path: str = LEASE_SOCKET):
        self._sock, self.fd = receive_lease(path)
        self._drm = _libdrm()
        drm = self._drm
        drm.drmSetClientCap(self.fd, _CAP_UNIVERSAL_PLANES, 1)
        # The leased plane is not the CRTC's legacy primary: SetCrtc is refused, atomic commits work.
        if drm.drmSetClientCap(self.fd, _CAP_ATOMIC, 1) != 0:
            raise LeaseError("no_atomic")
        self._crtc, self._plane, self._connector, self._mode = self._lease_objects()
        self.width, self.height = self._mode.timings[0], self._mode.timings[5]
        self._props = {
            "plane": self._properties(self._plane, _OBJECT_PLANE),
            "crtc": self._properties(self._crtc, _OBJECT_CRTC),
            "connector": self._properties(self._connector, _OBJECT_CONNECTOR),
        }
        self.buffers = [self._dumb_buffer() for _ in range(2)]
        self._shown = 0
        self._pending = False
        self._commit(self.buffers[0].fb_id, modeset=True)

    @property
    def back_index(self) -> int:
        return 1 - self._shown

    def present(self) -> None:
        self.wait_flip(timeout=0.1)
        target = 1 - self._shown
        self._commit(self.buffers[target].fb_id, modeset=False)
        self._shown = target
        self._pending = True

    def wait_flip(self, timeout: float) -> None:
        if self._pending and select.select([self.fd], [], [], timeout)[0]:
            self.drain()

    def drain(self) -> None:
        try:
            os.read(self.fd, 4096)
        except BlockingIOError:
            return
        self._pending = False

    def close(self) -> None:
        for buffer in self.buffers:
            buffer.memory.close()
        self._sock.close()

    def _lease_objects(self) -> tuple[int, int, int, _Mode]:
        drm = self._drm
        resources = drm.drmModeGetResources(self.fd)
        planes = drm.drmModeGetPlaneResources(self.fd)
        connector = None
        try:
            if not resources or not planes or resources.contents.count_crtcs < 1 or planes.contents.count_planes < 1 \
                    or resources.contents.count_connectors < 1:
                raise LeaseError("empty_lease")
            connector = drm.drmModeGetConnector(self.fd, resources.contents.connectors[0])
            if not connector or connector.contents.count_modes < 1:
                raise LeaseError("no_mode")
            return (resources.contents.crtcs[0], planes.contents.planes[0], connector.contents.connector_id,
                    _Mode.from_buffer_copy(connector.contents.modes[0]))
        finally:
            if connector:
                drm.drmModeFreeConnector(connector)
            if planes:
                drm.drmModeFreePlaneResources(planes)
            if resources:
                drm.drmModeFreeResources(resources)

    def _properties(self, obj: int, kind: int) -> dict[str, int]:
        drm = self._drm
        props = drm.drmModeObjectGetProperties(self.fd, obj, kind)
        if not props:
            raise LeaseError("no_properties")
        found = {}
        try:
            for index in range(props.contents.count_props):
                prop = drm.drmModeGetProperty(self.fd, props.contents.props[index])
                if prop:
                    found[prop.contents.name.decode()] = props.contents.props[index]
                    drm.drmModeFreeProperty(prop)
        finally:
            drm.drmModeFreeObjectProperties(props)
        return found

    def _dumb_buffer(self) -> Buffer:
        dumb = _CreateDumb(self.height, self.width, 32, 0, 0, 0, 0)
        fcntl.ioctl(self.fd, _IOCTL_CREATE_DUMB, dumb)
        mapping = _MapDumb(dumb.handle, 0, 0)
        fcntl.ioctl(self.fd, _IOCTL_MAP_DUMB, mapping)
        memory = mmap.mmap(self.fd, dumb.size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=mapping.offset)
        fb = C.c_uint32()
        if self._drm.drmModeAddFB(self.fd, self.width, self.height, 24, 32, dumb.pitch, dumb.handle, C.byref(fb)) != 0:
            raise LeaseError("add_fb_failed")
        return Buffer(fb.value, dumb.pitch, memory)

    def _commit(self, fb_id: int, modeset: bool) -> None:
        drm = self._drm
        request = drm.drmModeAtomicAlloc()
        plane, crtc, connector = self._props["plane"], self._props["crtc"], self._props["connector"]

        def put(obj: int, props: dict[str, int], name: str, value: int) -> None:
            drm.drmModeAtomicAddProperty(request, obj, props[name], value)

        try:
            if modeset:
                blob = C.c_uint32()
                drm.drmModeCreatePropertyBlob(self.fd, C.byref(self._mode), C.sizeof(self._mode), C.byref(blob))
                put(self._crtc, crtc, "MODE_ID", blob.value)
                put(self._crtc, crtc, "ACTIVE", 1)
                put(self._connector, connector, "CRTC_ID", self._crtc)
            put(self._plane, plane, "FB_ID", fb_id)
            put(self._plane, plane, "CRTC_ID", self._crtc)
            for name, value in (
                ("SRC_X", 0), ("SRC_Y", 0), ("SRC_W", self.width << 16), ("SRC_H", self.height << 16),
                ("CRTC_X", 0), ("CRTC_Y", 0), ("CRTC_W", self.width), ("CRTC_H", self.height),
            ):
                put(self._plane, plane, name, value)
            flags = _ATOMIC_ALLOW_MODESET if modeset else _ATOMIC_NONBLOCK | _PAGE_FLIP_EVENT
            if drm.drmModeAtomicCommit(self.fd, request, flags, None) != 0:
                code = C.get_errno()
                raise LeaseError(f"commit_failed:{errno.errorcode.get(code, code)}")
        finally:
            drm.drmModeAtomicFree(request)
