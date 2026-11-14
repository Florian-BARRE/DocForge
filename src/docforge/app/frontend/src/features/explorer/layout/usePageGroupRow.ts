// ====== Code Summary ======
// State of one Layout row: the shared block/chunk selection and the memoised derivations the view
// renders (reading-order indexes, the row's chunks, pages without layout, overlay boxes per page).
// The derivations themselves are pure functions in pageGroupModel.ts.

import { useCallback, useMemo, useState } from "react";

import type { ChunkInfo, IRBlock, PageInfo } from "../../../api/explorer";
import type { OverlayBox } from "../../../components/PageBoxOverlay";
import {
  activeChunkIdOf,
  buildBoxesByPage,
  chunksInRowOf,
  indexByBlockIdOf,
  noLayoutPagesOf,
  toggleSelection,
  type Selection,
} from "./pageGroupModel";

export interface PageGroupRowState {
  selectedBlockId: string | null;
  activeChunkId: string | null;
  chunksInRow: ChunkInfo[];
  noLayoutPages: Set<number>;
  boxesByPage: Map<number, OverlayBox[]>;
  selectBlock: (id: string) => void;
  selectChunk: (id: string) => void;
}

export function usePageGroupRow(
  pages: PageInfo[],
  blocks: IRBlock[],
  chunkByBlockId: Map<string, ChunkInfo>,
): PageGroupRowState {
  const [selected, setSelected] = useState<Selection | null>(null);

  const selectBlock = useCallback((id: string) => setSelected((prev) => toggleSelection(prev, "block", id)), []);
  const selectChunk = useCallback((id: string) => setSelected((prev) => toggleSelection(prev, "chunk", id)), []);

  const selectedBlockId = selected?.kind === "block" ? selected.id : null;
  const activeChunkId = activeChunkIdOf(selected, chunkByBlockId);
  const hasSelection = selected != null;

  // The block's number is its position in the row's continuous reading order — shared by the page box
  // badge and the middle card so they always agree.
  const indexByBlockId = useMemo(() => indexByBlockIdOf(blocks), [blocks]);
  const chunksInRow = useMemo(() => chunksInRowOf(blocks, chunkByBlockId), [blocks, chunkByBlockId]);
  const noLayoutPages = useMemo(() => noLayoutPagesOf(pages, blocks), [pages, blocks]);

  // Built once per relevant change (not on every render — a row can hold many blocks).
  const boxesByPage = useMemo(
    () =>
      buildBoxesByPage({
        pages, blocks, chunkByBlockId, indexByBlockId, noLayoutPages,
        activeChunkId, selectedBlockId, hasSelection,
        onSelectBlock: selectBlock, onSelectChunk: selectChunk,
      }),
    [pages, blocks, chunkByBlockId, activeChunkId, selectedBlockId, hasSelection, indexByBlockId, noLayoutPages, selectBlock, selectChunk],
  );

  return { selectedBlockId, activeChunkId, chunksInRow, noLayoutPages, boxesByPage, selectBlock, selectChunk };
}
