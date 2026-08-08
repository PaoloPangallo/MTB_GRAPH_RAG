# Cache-first and API-on-miss

`DocumentRuntime.open_live()` opens the writable authorized cache. A valid cached snapshot is used without a network call. A miss invokes the authorized resolver, persists the snapshot, records the manifest row, and continues the same run into parsing.

A second execution of the unseen validation case produced `cache_hit=1`, `network_fetch_count=0`. The first execution produced `cache_hit=0`, `network_fetch_count=1`.
