---
description: D13 — Data-fetching & cache hygiene. React-Query keys, staleTime, optimistic-update consistency.
weight: 8
---

You are sub-skill **D13 Cache Keys**. Standard contract.

## AUDIT

- **Query-key factory consistency**: find all `useQuery({ queryKey: [...] })` and `queryClient.invalidateQueries({ queryKey: [...] })` calls. Verify keys are produced by a single shared factory (e.g. `queryKeys.messages.list(fanId)`) and not built ad-hoc inline.
- **Mismatched invalidations**: for each `useMutation` with optimistic updates, check that `onSettled` invalidates the same key the `onMutate` snapshotted. List mismatches.
- **staleTime / refetchInterval audit**: `rg -n "staleTime:|refetchInterval:|gcTime:" src/` — list every value, group by config. Flag anomalies (e.g. `staleTime: 0` on data that's expensive to fetch).
- **Persistor coverage**: if `react-query-persist-client` / IDB persister is used, verify the keys persisted match the keys the UI reads on cold start. Mismatch = "loading flash".
- **Background refetch on focus / reconnect**: enabled by default in v5 — verify there's no global `refetchOnWindowFocus: false` that disables it silently.
- **Hover-prefetch hooks**: list components using a prefetch-on-hover hook; verify `staleTime` matches the consumer's `useQuery`.

For every file you read, append `"d13-cache-keys"` to `_file-coverage.json` `reviewed_by[]`.

## REPORT — `d13-cache-keys.md`

```
# D13 — Cache Keys — score x/10

## Query-key shape inventory
| Path-segment-1 | Variants | Consumers | Single factory? |

## Mismatched invalidations
…

## staleTime distribution
| staleTime | Count | Example call site |

## Persistor coverage gaps
…

## Findings
…

## Score reasoning
10 = single key factory + all invalidations match + staleTime consistent + persistor covers cold-start surface.
```

Cap at 400 lines.
