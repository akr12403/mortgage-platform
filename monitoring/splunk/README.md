# monitoring/splunk (M9 Task 9.3)

The Splunk side of observability is kept as code: what's in Splunk can be recreated from this folder.

| File | What |
| --- | --- |
| `dashboards/mortgage_platform_overview.xml` | Dashboard *Mortgage Platform: Service Health*, in Simple XML: payment SLI, payment p95, error count, request rate, 5xx rate, payment latency, consumer failures, latest errors (drill down by correlationId) |
| `alerts.json` | The 5 alerts (payment 5xx rate, payment p95 latency, payment fast burn, error spike, database unreachable), each with its runbook link |
| `fluent-bit/` | Log shipper configuration: Docker log driver → Splunk HEC (used by `docker-compose.splunk.yml`) |

Index: **`mortgage_dev`**. Sourcetype: **`mortgage:app:json`** (JSON fields extracted at search time). Field names are in the [log contract](../../docs/operations/observability.md#log-contract).

## Local Splunk (build and test)

```bash
bash scripts/splunk/local-up.sh          # Splunk + index + HEC token + dashboard + alerts + stack with log shipping
bash scripts/splunk/local-up.sh --down
```

The script generates the admin password and the HEC token into the git-ignored `.env.splunk-local`; nobody types or shares them. The UI is at http://localhost:8002.

To give the dashboard data, run `python3 scripts/splunk/traffic.py --minutes 5`. It sends about 2 requests per second across the four services, including 1.00 payments, and each request has its own correlation ID.

## Another Splunk (e.g. the instructor's)

1. **Ask for:**
   - an index named `mortgage_dev`, or the index name you've been given;
   - a HEC token allowed to write to it;
   - the HEC host and port.

   Store the token only in your shell or the git-ignored `.env`, never in a file that's committed.
2. **Ship the logs:**
   ```bash
   export SPLUNK_HEC_HOST=<host> SPLUNK_HEC_PORT=<port> SPLUNK_INDEX=mortgage_dev
   read -rs -p "HEC token: " SPLUNK_HEC_TOKEN; export SPLUNK_HEC_TOKEN; echo
   docker compose -f docker-compose.yml -f docker-compose.splunk.yml up -d
   ```
   TLS certificates are verified by default (`SPLUNK_HEC_TLS_VERIFY=On`).
3. **Dashboard:** in Splunk go to *Dashboards → Create New Dashboard → Classic Dashboards*, open *Source*, and paste `dashboards/mortgage_platform_overview.xml`.
4. **Alerts:** for each entry in `alerts.json`, go to *Search*, paste `search` with the time range *Last 5 minutes*, then *Save As → Alert*:
   - scheduled, cron `* * * * *`;
   - trigger when the number of results is greater than 0;
   - throttle 10 minutes;
   - action: add to Triggered Alerts;
   - put the runbook link in the description.

   If you have admin REST access, `python3 scripts/splunk/apply.py` applies both the dashboard and the alerts.
