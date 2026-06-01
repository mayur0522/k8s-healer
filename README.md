# 🔄 K8sHealer

**An autonomous AI agent that monitors Kubernetes clusters and automatically remediates common issues.**

[![Kubernetes](https://img.shields.io/badge/Kubernetes-326CE5?style=flat-square&logo=kubernetes&logoColor=white)]()
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)]()
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)]()
[![Gemini](https://img.shields.io/badge/Gemini_AI-4285F4?style=flat-square&logo=google&logoColor=white)]()

---

## 🎯 The Problem

Kubernetes clusters fail in predictable ways:
- Pods stuck in `CrashLoopBackOff`
- Nodes running out of disk space
- Memory leaks causing `OOMKilled`
- Deployments stuck in `Pending`

Engineers get paged, run the same commands, and apply the same fixes. **This is automatable.**

---

## ✨ How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                         K8sHealer                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [Watch Events] → [Match Pattern] → [AI Analysis] → [Fix]  │
│                                                             │
│  Knowledge Base:                                            │
│  • CrashLoopBackOff → Check logs → Restart/Rollback        │
│  • OOMKilled → Increase limits or HPA                       │
│  • DiskPressure → Clean up images → Alert                  │
│  • ImagePullBackOff → Check secret → Fix registry auth     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 🛡️ Self-Healing Capabilities

| Issue | Detection | Auto-Fix |
|-------|-----------|----------|
| **CrashLoopBackOff** | Pod restart count > threshold | Restart pod, rollback if persists |
| **OOMKilled** | Event watch + termination reason | Scale HPA, increase limits |
| **ImagePullBackOff** | Image pull failures | Verify secret, alert if registry down |
| **DiskPressure** | Node condition watch | Trigger image prune, clean old pods |
| **Pending Pods** | Pod stuck pending > 5min | Check node resources, scale node pool |
| **Failed Jobs** | Job status watch | Retry job, alert if max retries |
| **Certificate Expiry** | Secret watch + TLS check | Trigger cert-manager renewal |

---

## 🚀 Quick Start

### Prerequisites
- Kubernetes cluster with appropriate RBAC
- Python 3.11+
- Gemini API key (for AI-powered analysis)

### 1. Clone the repository
```bash
git clone https://github.com/mayur0522/k8s-healer.git
cd k8s-healer
```

### 2. Deploy to cluster
```bash
# Create namespace
kubectl create namespace k8s-healer

# Create secrets
kubectl create secret generic ai-config \
  --from-literal=GEMINI_API_KEY=your_key \
  -n k8s-healer

# Deploy agent
kubectl apply -f deploy/
```

### 3. Monitor logs
```bash
kubectl logs -f deployment/k8s-healer -n k8s-healer
```

---

## 📁 Project Structure

```
k8s-healer/
├── src/
│   ├── main.py              # Main controller loop
│   ├── watchers/
│   │   ├── pod_watcher.py   # Pod event watcher
│   │   ├── node_watcher.py  # Node condition watcher
│   │   └── event_watcher.py # Kubernetes event stream
│   ├── healers/
│   │   ├── pod_healer.py    # Pod remediation
│   │   ├── node_healer.py   # Node remediation
│   │   └── deployment_healer.py
│   ├── ai/
│   │   └── analyzer.py      # AI-powered root cause analysis
│   └── knowledge/
│       └── patterns.yaml    # Known issue patterns
├── deploy/
│   ├── deployment.yaml
│   ├── rbac.yaml
│   └── configmap.yaml
├── docker-compose.yml       # For local testing
├── Dockerfile
└── requirements.txt
```

---

## ⚙️ Configuration

### Healing Rules (config/rules.yaml)

```yaml
rules:
  - name: crash_loop_backoff
    condition:
      type: pod_status
      status: CrashLoopBackOff
      restart_count: ">= 5"
    actions:
      - type: analyze_logs
      - type: restart_pod
        if_fails: rollback_deployment
    cooldown: 300  # 5 minutes between actions
    
  - name: oom_killed
    condition:
      type: termination_reason
      reason: OOMKilled
    actions:
      - type: increase_memory_limit
        factor: 1.5
      - type: notify
        channel: "#k8s-alerts"
    max_increases: 3
```

### RBAC Permissions

The agent needs these permissions:
```yaml
rules:
  - apiGroups: [""]
    resources: ["pods", "pods/log", "events", "nodes"]
    verbs: ["get", "list", "watch", "delete"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets"]
    verbs: ["get", "list", "watch", "patch", "update"]
```

---

## 🔒 Safety Features

| Feature | Description |
|---------|-------------|
| **Cooldown Periods** | Prevents action loops (default 5 min) |
| **Max Actions** | Limits fixes per hour per resource |
| **Dry Run Mode** | Test without making changes |
| **Namespace Filtering** | Exclude kube-system by default |
| **Audit Logging** | All actions logged for review |
| **Slack Notifications** | Real-time alerts for all actions |

---

## 📊 Metrics & Monitoring

The agent exposes Prometheus metrics:

```
# HELP healing_actions_total Total healing actions taken
# TYPE healing_actions_total counter
healing_actions_total{action="restart_pod",result="success"} 42

# HELP healing_issues_detected Issues detected by type
# TYPE healing_issues_detected counter
healing_issues_detected{type="CrashLoopBackOff"} 15

# HELP healing_action_duration_seconds Time to complete healing action
# TYPE healing_action_duration_seconds histogram
healing_action_duration_seconds_bucket{le="1"} 100
```

---

## 🤝 Freelance Services

Need K8sHealer for your specific stack?

- **Custom Healing Rules:** Tailored to your application behavior
- **Integration:** Connect to PagerDuty, OpsGenie, etc.
- **Multi-Cluster:** Manage healing across multiple clusters

[**Contact Me**](mailto:mayurbhosalen9@gmail.com)

---

## 📄 License

MIT License
