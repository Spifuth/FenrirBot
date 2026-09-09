# Grafana Webhook Contact Point Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Grafana's alerting system to FenrirBot's existing `/webhook/grafana` endpoint so firing alerts are posted to Discord automatically.

**Architecture:** FenrirBot already has a fully functional Grafana webhook handler at `POST /webhook/grafana` (supporting both unified and legacy formats). This plan is purely configuration: clean up dead env vars from the compose file, configure a Grafana contact point pointing to `http://fenrirbot:8085/webhook/grafana`, and wire it into a notification policy.

**Tech Stack:** Grafana UI (Alerting → Contact Points), Docker Compose, Infisical secrets, aiohttp (already running)

---

## Network context

FenrirBot (`fenrirbot` container) and Grafana (`grafana` container) both share the `t3_proxy` Docker network. They can reach each other by container name:

- Grafana → FenrirBot webhook: `http://fenrirbot:8085/webhook/grafana`
- Authentication: add `Authorization: Bearer <WEBHOOK_SECRET>` header in the contact point

---

### Task 1: Clean dead env vars from the FenrirBot compose file

**Files:**
- Modify: `/srv/nebula/docker/services/management/fenrirbot/fenrirbot.yml`

The compose file still declares `REPORTS_CHANNEL_ID`, `UPTIMEKUMA_URL`, `UPTIMEKUMA_USERNAME`, `UPTIMEKUMA_PASSWORD`, `UPTIMEKUMA_AUTO_PAUSE`, and `NETDATA_URL` — all removed from `config.py` in the dead-code cleanup. These are harmless but confusing.

- [ ] **Step 1: Remove dead env vars from the compose file**

In `/srv/nebula/docker/services/management/fenrirbot/fenrirbot.yml`, delete these lines from the `environment:` block:

```yaml
      REPORTS_CHANNEL_ID: ${FENRIRBOT_REPORTS_CHANNEL_ID}
      UPTIMEKUMA_URL: ${FENRIRBOT_UPTIMEKUMA_URL}
      UPTIMEKUMA_USERNAME: ${FENRIRBOT_UPTIMEKUMA_USERNAME}
      UPTIMEKUMA_PASSWORD: ${FENRIRBOT_UPTIMEKUMA_PASSWORD}
      UPTIMEKUMA_AUTO_PAUSE: "true"
      NETDATA_URL: http://host-gateway:19999
```

The file after the edit should have only these in `environment:`:

```yaml
    environment:
      TZ: ${TZ}
      DISCORD_TOKEN: ${FENRIRBOT_DISCORD_TOKEN}
      ANNOUNCEMENT_CHANNEL_ID: ${FENRIRBOT_ANNOUNCEMENT_CHANNEL_ID}
      NOTIFICATION_ROLE_ID: ${FENRIRBOT_NOTIFICATION_ROLE_ID}
      DOCKER_HOST: tcp://socket-proxy:2375
      WEBHOOK_ENABLED: "true"
      WEBHOOK_HOST: "0.0.0.0"
      WEBHOOK_PORT: "8085"
      WEBHOOK_SECRET: ${FENRIRBOT_WEBHOOK_SECRET}
```

- [ ] **Step 2: Commit**

```bash
cd /srv/nebula
git add docker/services/management/fenrirbot/fenrirbot.yml
git commit -m "chore(fenrirbot): remove dead env vars (uptimekuma, netdata, reports)"
```

Expected: 1 file changed, 6 deletions.

---

### Task 2: Retrieve the WEBHOOK_SECRET value

You need the current `FENRIRBOT_WEBHOOK_SECRET` value to configure the Authorization header in Grafana.

- [ ] **Step 1: Read the secret from Infisical**

```bash
source /srv/nebula/.infisical-auth
INFISICAL_TOKEN="$INFISICAL_ACCESS_TOKEN" infisical secrets get \
  FENRIRBOT_WEBHOOK_SECRET \
  --projectId b13d9e15-c37e-462d-b695-5ebb96b7bda4 \
  --domain "$INFISICAL_DOMAIN" \
  --env prod
```

Note the value — you will paste it into Grafana in the next task.

---

### Task 3: Configure Grafana contact point

- [ ] **Step 1: Open Grafana → Alerting → Contact points**

Navigate to `https://grafana.<your-domain>/alerting/notifications`.

- [ ] **Step 2: Add a new contact point**

Click **"+ Add contact point"** and fill in:

| Field | Value |
|-------|-------|
| Name | `FenrirBot Discord` |
| Integration | `Webhook` |
| URL | `http://fenrirbot:8085/webhook/grafana` |
| HTTP Method | `POST` |

Under **"Optional Webhook settings"** → **"Authorization"**:

| Field | Value |
|-------|-------|
| Credentials | `Bearer token` |
| Token | `<value from Task 2>` |

- [ ] **Step 3: Test the contact point**

Click **"Test"** in the Grafana UI. Grafana will send a test payload to FenrirBot.

Expected: A Discord embed appears in the configured announcement channel within a few seconds. It will say something like `[TEST] Grafana Alert` — the existing `handle_grafana` handler processes this automatically.

If no message appears in Discord, check FenrirBot logs:

```bash
docker logs fenrirbot --tail 50
```

- [ ] **Step 4: Save the contact point**

Click **"Save contact point"**.

---

### Task 4: Wire the contact point into a notification policy

- [ ] **Step 1: Open Grafana → Alerting → Notification policies**

Navigate to `https://grafana.<your-domain>/alerting/routes`.

- [ ] **Step 2: Edit the default policy**

Click the **"..."** menu on the **Default policy** and select **"Edit"**.

Change **"Default contact point"** to `FenrirBot Discord`.

Click **"Update default policy"**.

> **Tip:** If you only want specific alerts to go to Discord (not all of them), create a child policy with matchers (e.g., `severity = critical`) pointing to `FenrirBot Discord`, and leave the default policy unchanged.

---

### Task 5: Verify end-to-end with a real alert

- [ ] **Step 1: Check that at least one alert rule exists**

Navigate to **Alerting → Alert rules**. If none exist, create a simple test rule:
- Condition: `avg(node_cpu_seconds_total) > -1` (always fires)
- For: `0s` (fires immediately)

- [ ] **Step 2: Wait for the alert to fire and verify Discord**

The alert should appear in the announcement channel as an embed with color/severity info from `handle_grafana`.

- [ ] **Step 3: Delete the test rule if you created one**

Go back to Alert rules and delete the test rule.

---

### Task 6: Push to git

```bash
cd /srv/nebula
git push
```

Expected: clean push with 1 new commit.
