// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ find: vi.fn(), close: vi.fn(), modal: vi.fn(), log: vi.fn() }));
vi.mock('@decky/ui', () => ({ findSP: mocks.find, Navigation: { CloseSideMenus: mocks.close }, ButtonItem: ({children, ...props}: {children?: ReactNode}) => <button {...props}>{children}</button>, DialogButton: ({children, ...props}: {children?: ReactNode}) => <button {...props}>{children}</button>, ModalRoot: ({children}: {children?: ReactNode}) => <div>{children}</div> }));
vi.mock('../navigation/showModal', () => ({showModal: mocks.modal}));
vi.mock('../system/uiEvents', () => ({recordUiEvent: mocks.log}));
vi.mock('../i18n', () => ({useI18n: () => ({lang:'es'})}));
import { DuoDockEditorButton, openDuoDockEditor } from './DuoDockEditorButton';
afterEach(() => {cleanup(); vi.clearAllMocks(); vi.unstubAllGlobals();});
it('opens on the Steam document only when runtime accepts and permits reopening on close', () => {
  const doc=document.implementation.createHTMLDocument(); mocks.find.mockReturnValue({document:doc});
  let close: (()=>void)|undefined;
  doc.addEventListener('pdc-duo-dock-open', event => {expect(event.cancelable).toBe(true); event.preventDefault(); close=(event as CustomEvent).detail.onClose;});
  expect(openDuoDockEditor(true)).toBe(true); expect(mocks.close).toHaveBeenCalledTimes(1);
  expect(openDuoDockEditor(true)).toBe(false); close?.(); close?.();
  expect(mocks.log.mock.calls.filter(call => call[1] === 'duo_dock_editor_closed')).toHaveLength(1);
  expect(openDuoDockEditor(true)).toBe(true); close?.();
  expect(mocks.log).toHaveBeenCalledWith('themes','duo_dock_editor_opened',{},true);
});
it('shows a visible failure and records it when runtime is missing', () => {
  mocks.find.mockReturnValue({document:document.implementation.createHTMLDocument()});
  expect(openDuoDockEditor(true)).toBe(false); expect(mocks.close).not.toHaveBeenCalled();
  render(mocks.modal.mock.calls[0][0]); expect(screen.getByRole('alert').textContent).toContain('No se pudo abrir');
  expect(mocks.log).toHaveBeenCalledWith('themes','duo_dock_editor_failed',{},false);
});
it('records document access failure without leaving the editor locked', () => {
  mocks.find.mockImplementation(()=>{throw new Error('unavailable');});
  expect(openDuoDockEditor(false)).toBe(false); expect(openDuoDockEditor(false)).toBe(false); expect(mocks.modal).toHaveBeenCalledTimes(2);
});
it('closes the manager before dispatching and obeys disabled state', () => {
  mocks.find.mockReturnValue({document:document.implementation.createHTMLDocument()});
  const frames: FrameRequestCallback[]=[]; vi.stubGlobal('requestAnimationFrame',(callback:FrameRequestCallback)=>{frames.push(callback);return 1;});
  const onOpen=vi.fn(); const view=render(<DuoDockEditorButton onOpen={onOpen} disabled />);
  fireEvent.click(screen.getByRole('button')); expect(onOpen).not.toHaveBeenCalled();
  view.rerender(<DuoDockEditorButton onOpen={onOpen} />); fireEvent.click(screen.getByRole('button')); expect(onOpen).toHaveBeenCalledTimes(1); expect(mocks.find).not.toHaveBeenCalled();
  vi.spyOn(Date,'now').mockReturnValue(Date.now()+2000); frames[0](0); vi.restoreAllMocks(); expect(mocks.find).toHaveBeenCalledTimes(1);
});
