import { useState } from "react";
import type { LibraryAsset } from "@framebase/web-contracts";
import { imageUrl } from "../library/api";
import { folderPath, formatBytes } from "../library/folderTree";
import { useLibrary } from "../library/LibraryContext";
import { LoadMore } from "./LoadMore";

function Thumb({ asset, variant }: { asset: LibraryAsset; variant: "grid-256" | "grid-512" }) {
  const [failed, setFailed] = useState(false);
  if (failed) return <span className="thumb thumb--missing">No preview</span>;
  return (
    <img
      className="thumb"
      loading="lazy"
      decoding="async"
      src={imageUrl(asset.id, variant)}
      alt={asset.displayName}
      onError={() => setFailed(true)}
    />
  );
}

export function GridView() {
  const { assets, selected, select } = useLibrary();
  return (
    <>
      <ul className="grid">
        {assets.map((asset) => (
          <li key={asset.id}>
            <button
              type="button"
              className={`tile${selected?.id === asset.id ? " is-active" : ""}`}
              onClick={() => select(asset)}
              aria-pressed={selected?.id === asset.id}
            >
              <Thumb asset={asset} variant="grid-256" />
              <span className="tile-name">{asset.displayName}</span>
            </button>
          </li>
        ))}
      </ul>
      <LoadMore />
    </>
  );
}

export function ListView() {
  const { assets, structure, selected, select } = useLibrary();
  const folders = structure?.folders ?? [];
  return (
    <>
      <table className="list">
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Folder</th>
            <th scope="col">Type</th>
            <th scope="col">Size</th>
            <th scope="col">Tags</th>
          </tr>
        </thead>
        <tbody>
          {assets.map((asset) => (
            <tr key={asset.id} className={selected?.id === asset.id ? "is-active" : undefined}>
              <th scope="row">
                <button type="button" className="row-button" onClick={() => select(asset)}>
                  {asset.displayName}
                </button>
              </th>
              <td>{folderPath(folders, asset.folderId)}</td>
              <td>{asset.mediaType}</td>
              <td>{formatBytes(asset.byteSize)}</td>
              <td>{asset.tags.length}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <LoadMore />
    </>
  );
}
