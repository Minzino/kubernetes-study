# Monitoring Stack

## 📌 Overview

This Helm Chart deploys a complete monitoring stack using:

- Prometheus Operator
- Prometheus
- Grafana
- Loki
- Promtail
- Node Exporter
- Kube State Metrics

## 🚀 Installation

```bash
kind create cluster --config kind-config.yaml
helm upgrade --install monitoring-stack ./monitoring-stack
```

## 🌐 Web Access

### Grafana: http://localhost:30300

### Prometheus: http://localhost:30090

---

## 🎯 **MacBook에서 직접 접속**

✅ **NodePort 사용 → MacBook 웹 브라우저에서 바로 접근 가능**

- **Grafana:** `http://localhost:30300`
- **Prometheus:** `http://localhost:30090`

---