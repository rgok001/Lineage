import MapTabs from "./tabs";

/**
 * The frame every route under one map shares (issue #143).
 *
 * DO NOT FETCH ANYTHING IN THIS LAYOUT. `await params` is fine — that is
 * routing, not I/O. Nothing else may be awaited here. A layout that reads data
 * blocks navigation *above* the loading boundary, because `loading.tsx` nests
 * inside `layout.tsx` and cannot cover its parent: the reader would get the
 * 2-3s blank wait back on every route under a map, with the skeletons #140
 * bought still painting underneath it, and it would look like #140 regressing
 * for no visible reason. The map's name and a menu of thread names were both
 * asked for and both refused on exactly this mechanic.
 *
 * The strip is here rather than in each page so that a sideways click reuses
 * this layout and only swaps the leaf: the strip stays mounted and interactive,
 * and the four links are permanently in the viewport, which is the only reason
 * the router prefetches them at all (5-14ms in-viewport against 349ms below
 * the fold, measured on the live site for #143).
 */
export default async function MapLayout({
  children, params,
}: { children: React.ReactNode; params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <>
      <MapTabs id={id} />
      {children}
    </>
  );
}
