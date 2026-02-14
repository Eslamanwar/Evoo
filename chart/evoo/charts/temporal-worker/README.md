# Temporal Worker Subchart

This subchart deploys a Temporal worker for the AWS Cost Analysis Agent.

## Resources Created

- **ServiceAccount**: Kubernetes service account for the worker
- **Service**: ClusterIP service exposing port 80
- **Deployment**: Worker deployment running the temporal worker
- **HorizontalPodAutoscaler**: Auto-scaling based on CPU utilization

## Configuration

The temporal-worker subchart inherits global values from the parent chart:
- `global.agentName`: Name of the agent
- `global.agentDescription`: Description of the agent
- `global.temporalAddress`: Temporal server address
- `global.agentexBaseUrl`: AgentEx base URL
- `global.workflowTaskQueue`: Workflow task queue name
- `global.workflowName`: Workflow name
- `global.acpType`: ACP type (async)
- `global.acpPort`: ACP port

## Default Values

See `values.yaml` for all configurable options including:
- Image configuration
- Resource limits and requests
- Autoscaling settings
- Environment variables
- Probe configurations
- Service account token volume settings

## Usage

The subchart is automatically enabled in the parent chart. To disable:

```yaml
temporal-worker:
  enabled: false
```

To override default values:

```yaml
temporal-worker:
  resources:
    limits:
      cpu: 1000m
      memory: 1Gi
  autoscaling:
    minReplicas: 2
    maxReplicas: 20
