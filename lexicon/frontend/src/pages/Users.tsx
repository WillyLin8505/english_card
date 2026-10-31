import { Fragment, useState } from "react";
import { Empty, ErrorBox, Loading, fmtTime, useLoad } from "../ui";

type U = {
  id: number;
  email: string | null;
  provider: string;
  blocked: boolean;
  joined: string | null;
  albums: string[];
  album_count: number;
  reviews_total: number;
  reviews_7d: number;
  photos_taken: number;
  photos_opened: number;
  app_version: string | null;
  last_seen: string | null;
};
type Overview = { total_users: number; active_7d: number; matched: number; users: U[] };

const COLS: [string, string][] = [
  ["email", "Email"],
  ["album_count", "相片冊"],
  ["reviews_total", "複習累計"],
  ["reviews_7d", "近 7 天複習"],
  ["photos_taken", "拍攝照片"],
  ["photos_opened", "打開照片"],
  ["last_seen", "最後使用"],
];

export default function Users() {
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("last_seen");
  const [desc, setDesc] = useState(true);
  const [open, setOpen] = useState<number | null>(null);
  const data = useLoad<Overview>(`/admin/users?q=${encodeURIComponent(q)}&sort=${sort}&desc=${desc}`, [q, sort, desc], 15000);

  const pick = (k: string) => {
    if (k === sort) setDesc(!desc);
    else {
      setSort(k);
      setDesc(k !== "email");
    }
  };

  return (
    <div className="page page-wide">
      <header className="page-head">
        <div>
          <h1>使用者（Users）</h1>
          <p className="muted">
            只有登入雲端帳號的使用者會回傳數字（相片冊名稱、複習／照片次數），沒登入的人這裡看不到。不含照片與單字內容；除了 email 沒有其他個資。
          </p>
        </div>
      </header>
      {data.error && <ErrorBox error={data.error} />}
      {!data.data ? (
        <Loading />
      ) : (
        <>
          <section className="card form-inline">
            <span>總人數 <b>{data.data.total_users}</b></span>
            <span>近 7 天活躍 <b>{data.data.active_7d}</b></span>
            <input placeholder="搜尋 email 或相片冊名稱" value={q} onChange={(e) => setQ(e.target.value)} />
          </section>
          {data.data.users.length === 0 ? (
            <Empty>沒有符合的使用者</Empty>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  {COLS.map(([k, label]) => (
                    <th key={k} style={{ cursor: "pointer" }} onClick={() => pick(k)}>
                      {label}{sort === k ? (desc ? " ▼" : " ▲") : ""}
                    </th>
                  ))}
                  <th>版本</th>
                </tr>
              </thead>
              <tbody>
                {data.data.users.map((u) => (
                  <Fragment key={u.id}>
                    <tr style={{ cursor: "pointer" }} onClick={() => setOpen(open === u.id ? null : u.id)}>
                      <td>{u.email ?? `(${u.provider})`}{u.blocked ? " ⛔" : ""}</td>
                      <td>{u.album_count}</td>
                      <td>{u.reviews_total}</td>
                      <td>{u.reviews_7d}</td>
                      <td>{u.photos_taken}</td>
                      <td>{u.photos_opened}</td>
                      <td>{u.last_seen ? fmtTime(u.last_seen) : "—"}</td>
                      <td>{u.app_version ?? "—"}</td>
                    </tr>
                    {open === u.id && (
                      <tr>
                        <td colSpan={8}>
                          <div>註冊：{fmtTime(u.joined)}　登入方式：{u.provider}</div>
                          <div>下載的相片冊（{u.album_count}）：{u.albums.length ? u.albums.join("、") : "—"}</div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
