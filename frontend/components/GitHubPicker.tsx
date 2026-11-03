"use client";
import { useCallback, useEffect, useState } from "react";
type Item = {
  name?: string;
  label?: string;
  url: string;
  revision?: string;
  private?: boolean;
};
type Status = {
  configured: boolean;
  connected: boolean;
  login?: string;
  installation_url?: string;
};
export default function GitHubPicker({
  request,
  onSelect,
}: {
  request: (path: string, init?: RequestInit) => Promise<unknown>;
  onSelect: (url: string, revision: string) => void;
}) {
  const api = useCallback(
    async <T,>(path: string, init?: RequestInit): Promise<T> =>
      (await request(path, init)) as T,
    [request],
  );
  const [status, setStatus] = useState<Status | null>(null),
    [repos, setRepos] = useState<Item[]>([]),
    [targets, setTargets] = useState<Item[]>([]);
  const [repo, setRepo] = useState(""),
    [kind, setKind] = useState("branches"),
    [query, setQuery] = useState(""),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1),
    [more, setMore] = useState(false),
    [targetPage, setTargetPage] = useState(1),
    [targetMore, setTargetMore] = useState(false);
  useEffect(() => {
    let active = true;
    api<Status>("/github/status")
      .then((s) => {
        if (active) setStatus(s);
      })
      .catch((e) => {
        if (active) setError(String(e));
      });
    return () => {
      active = false;
    };
  }, [api]);
  useEffect(() => {
    if (!status?.connected) return;
    let active = true;
    Promise.resolve().then(() => {
      if (active) {
        setLoading(true);
        setError("");
      }
    });
    api<{ items: Item[]; has_more: boolean }>(
      "/github/repositories?page=" + page,
    )
      .then((data) => {
        if (active) {
          setRepos((old) =>
            page === 1 ? data.items : [...old, ...data.items],
          );
          setMore(data.has_more);
        }
      })
      .catch((e) => {
        if (active) setError(String(e));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [status?.connected, page, api]);
  useEffect(() => {
    if (!repo) return;
    let active = true;
    Promise.resolve().then(() => {
      if (active) {
        setLoading(true);
        setError("");
      }
    });
    api<{ items: Item[]; has_more: boolean }>(
      "/github/repositories/" + repo + "/" + kind + "?page=" + targetPage,
    )
      .then((data) => {
        if (active) {
          setTargets(data.items);
          setTargetMore(data.has_more);
        }
      })
      .catch((e) => {
        if (active) setError(String(e));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [repo, kind, targetPage, api]);
  async function connect() {
    setLoading(true);
    setError("");
    try {
      const data = await api<{ url: string }>("/github/connect", {
        method: "POST",
      });
      window.location.assign(data.url);
    } catch (e) {
      setError(String(e));
      setLoading(false);
    }
  }
  if (!status)
    return <p role="status">{error || "Checking GitHub connection…"}</p>;
  return (
    <div className="space-y-4">
      {status.connected ? (
        <div className="flex gap-4 items-center">
          <span>
            Connected as <strong>{status.login}</strong>
          </span>
          <button
            type="button"
            className="underline text-sm"
            onClick={async () => {
              try {
                await request("/github/disconnect", { method: "POST" });
                setStatus({ ...status, connected: false });
                setRepos([]);
                setRepo("");
              } catch (e) {
                setError(String(e));
              }
            }}
          >
            Disconnect
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <p>Connect GitHub to browse the repositories you grant access to.</p>
          <button
            type="button"
            disabled={loading}
            onClick={() => void connect()}
            className="bg-stone-200 text-stone-900 rounded px-5 py-3 disabled:opacity-50"
          >
            Connect GitHub
          </button>
          {!status.configured && (
            <p className="text-sm text-orange-800">
              GitHub connection needs server setup. You can paste a public
              GitHub URL now.
            </p>
          )}
        </div>
      )}
      {status.connected && (
        <>
          <input
            aria-label="Search repositories"
            placeholder="Search loaded repositories…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="bg-stone-100 border rounded p-3 w-full"
          />
          <select
            aria-label="GitHub repository"
            value={repo}
            onChange={(e) => {
              setTargets([]);
              setRepo(e.target.value);
              setTargetPage(1);
              onSelect("", "");
            }}
            className="bg-stone-100 border rounded p-3 w-full"
          >
            <option value="">Choose a repository</option>
            {repos
              .filter((r) =>
                r.name?.toLowerCase().includes(query.toLowerCase()),
              )
              .map((r) => (
                <option key={r.name} value={r.name}>
                  {r.name}
                  {r.private ? " · Private" : ""}
                </option>
              ))}
          </select>
          {more && (
            <button
              type="button"
              className="underline"
              disabled={loading}
              onClick={() => setPage((p) => p + 1)}
            >
              Load more repositories
            </button>
          )}
          {!loading && !repos.length && (
            <p>
              No repositories available. Install the GitHub App and grant
              repository access.
            </p>
          )}
          {status.installation_url && (
            <a
              className="underline text-sm"
              href={status.installation_url}
              target="_blank"
              rel="noreferrer"
            >
              Manage repository access
            </a>
          )}
          {repo && (
            <>
              <div className="flex gap-2 flex-wrap">
                {[
                  ["branches", "Whole project"],
                  ["pulls", "Pull request"],
                  ["commits", "Commit"],
                ].map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    aria-pressed={kind === value}
                    className={
                      "rounded px-3 py-2 border " +
                      (kind === value ? "bg-stone-300" : "border-stone-300")
                    }
                    onClick={() => {
                      setTargets([]);
                      setKind(value);
                      setTargetPage(1);
                      onSelect("", "");
                    }}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <select
                key={repo + kind + targetPage}
                defaultValue=""
                aria-label="GitHub review target"
                onChange={(e) => {
                  const t = targets[Number(e.target.value)];
                  if (t) onSelect(t.url, t.revision || "");
                }}
                className="bg-stone-100 border rounded p-3 w-full"
              >
                <option value="" disabled>
                  Choose{" "}
                  {kind === "branches"
                    ? "a branch"
                    : kind === "pulls"
                      ? "an open PR"
                      : "a commit"}
                </option>
                {targets.map((t, i) => (
                  <option key={i} value={i}>
                    {t.label}
                  </option>
                ))}
              </select>
              {!loading && !targets.length && <p>No {kind} available.</p>}
              <div className="flex gap-4">
                {targetPage > 1 && (
                  <button
                    type="button"
                    className="underline"
                    onClick={() => {
                      onSelect("", "");
                      setTargetPage((p) => p - 1);
                    }}
                  >
                    Previous
                  </button>
                )}
                {targetMore && (
                  <button
                    type="button"
                    className="underline"
                    onClick={() => {
                      onSelect("", "");
                      setTargetPage((p) => p + 1);
                    }}
                  >
                    Next
                  </button>
                )}
              </div>
            </>
          )}
        </>
      )}
      {loading && <p role="status">Loading GitHub…</p>}
      {error && (
        <p role="alert" className="text-orange-800">
          {error}
        </p>
      )}
    </div>
  );
}
