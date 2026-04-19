---
name: Bug report
about: Report an issue with the integration
title: ''
labels: ''
assignees: ''

---

**Describe the bug**
A clear and concise description of what's wrong and what you expected.

**Environment**
- Home Assistant version (Settings → About):
- Flightradar24 integration version (`manifest.json` or HACS):
- Installation type: HAOS / Container / Core / Supervised

**Reproduction steps**
1.
2.

**Diagnostics dump**
Settings → Devices & Services → Flightradar24 → ⋮ → *Download diagnostics*.
Attach the JSON file. (Credentials and coordinates are redacted automatically.)

**Logs**
Enable debug logging, reproduce the issue, then paste the relevant lines:

```yaml
# configuration.yaml
logger:
  default: warning
  logs:
    custom_components.flightradar24: debug
```

Logs live at Settings → System → Logs (or `home-assistant.log`).

**Entity state (if the issue is about a specific entity)**
Developer Tools → States → paste the relevant entity's state + attributes.
