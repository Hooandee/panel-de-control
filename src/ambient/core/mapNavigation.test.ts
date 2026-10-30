import { describe, expect, it } from "vitest";

import { dotRadius, nearestCode, nextPoint, project, stepZoom, unproject, viewBoxFor, viewRadiusKm, type MapPoint } from "./mapNavigation";

const ES: MapPoint = { code: "ES", x: 480, y: 150 };
const FR: MapPoint = { code: "FR", x: 490, y: 130 };
const PT: MapPoint = { code: "PT", x: 470, y: 152 };
const IT: MapPoint = { code: "IT", x: 515, y: 150 };
const MA: MapPoint = { code: "MA", x: 478, y: 180 };
const US: MapPoint = { code: "US", x: 220, y: 140 };
const ALL = [ES, FR, PT, IT, MA, US];

describe("map navigation", () => {
  it("moves to the neighbour that way", () => {
    expect(nextPoint(ES, ALL, "up")).toBe("FR");
    expect(nextPoint(ES, ALL, "left")).toBe("PT");
    expect(nextPoint(ES, ALL, "right")).toBe("IT");
    expect(nextPoint(ES, ALL, "down")).toBe("MA");
  });

  it("jumps oceans when nothing is closer", () => {
    expect(nextPoint(PT, [PT, US, IT], "left")).toBe("US");
  });

  it("returns null at the edge so focus can leave the map", () => {
    expect(nextPoint(US, [US, ES], "left")).toBeNull();
    expect(nextPoint(MA, [MA, FR], "down")).toBeNull();
  });

  it("ignores points far off the axis", () => {
    expect(nextPoint({ code: "A", x: 0, y: 0 }, [{ code: "B", x: 10, y: 100 }], "right")).toBeNull();
  });

  it("scales dots logarithmically", () => {
    expect(dotRadius(0, 3000)).toBe(0);
    expect(dotRadius(3000, 3000)).toBeCloseTo(10);
    expect(dotRadius(3, 3000)).toBeGreaterThan(2.2);
    expect(dotRadius(3, 3000)).toBeLessThan(dotRadius(300, 3000));
  });

  it("frames the zoom around a point without leaving the world", () => {
    expect(viewBoxFor(1, { x: 480, y: 150 }, 1000, 500)).toEqual({ x: 0, y: 0, width: 1000, height: 500 });
    expect(viewBoxFor(4, { x: 480, y: 150 }, 1000, 500)).toEqual({ x: 355, y: 87.5, width: 250, height: 125 });
    expect(viewBoxFor(4, { x: 5, y: 5 }, 1000, 500)).toMatchObject({ x: 0, y: 0 });
    expect(viewBoxFor(8, { x: 999, y: 499 }, 1000, 500)).toMatchObject({ x: 875, y: 437.5 });
  });

  it("steps through zoom levels and stops at the ends", () => {
    expect(stepZoom(1, 1)).toBe(2);
    expect(stepZoom(8, 1)).toBe(16);
    expect(stepZoom(64, 1)).toBe(128);
    expect(stepZoom(512, 1)).toBe(512);
    expect(stepZoom(1, -1)).toBe(1);
    expect(stepZoom(4, -1)).toBe(2);
  });

  it("projects coordinates like the bundled outlines", () => {
    expect(project(84, -180)).toEqual({ x: 0, y: 0 });
    expect(project(-58, 180)).toEqual({ x: 1000, y: 500 });
    const madrid = project(40.4168, -3.7038);
    expect(madrid.x).toBeCloseTo(489.7, 1);
    expect(madrid.y).toBeCloseTo(153.5, 1);
  });

  it("finds the country closest to the view centre", () => {
    expect(nearestCode({ x: 485, y: 150 }, ALL)).toBe("ES");
    expect(nearestCode({ x: 0, y: 0 }, [])).toBeNull();
  });

  it("unprojects back to the same coordinates", () => {
    const { x, y } = project(37.389, -5.984);
    const back = unproject(x, y);
    expect(back.lat).toBeCloseTo(37.389, 3);
    expect(back.lon).toBeCloseTo(-5.984, 3);
  });

  it("sizes the search radius to what is on screen", () => {
    const city = viewRadiusKm(1000 / 256, 37.4);
    expect(city).toBeGreaterThan(40);
    expect(city).toBeLessThan(80);
    expect(viewRadiusKm(0.001, 37.4)).toBe(5);
  });
});

