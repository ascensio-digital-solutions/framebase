const SECTIONS = ["Folders", "Albums", "Tags", "Saved searches", "Trash"];

export function ExplorerPanel() {
  return (
    <>
      <ul className="explorer-list">
        {SECTIONS.map((name) => (
          <li key={name}>{name}</li>
        ))}
      </ul>
      <p className="muted">Connects to the Framebase catalog in the library workspace milestone.</p>
    </>
  );
}
