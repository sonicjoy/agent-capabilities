---
name: access-kube-pod
description: Access Kubernetes pods on AWS EKS clusters via kubectl. Handles AWS SSO authentication, EKS context setup, namespace listing, pod discovery, and interactive shell access. Use when the user wants to connect to a pod, exec into a container, access EKS, or work with Kubernetes.
---

# Access Kube Pod

Guide users through accessing Kubernetes pods on AWS EKS clusters.

## Workflow

### Step 1: Determine AWS Profile

Ask which AWS profile to use:

```
Which AWS profile should I use to connect to EKS?
```

Common profiles: `production`, `staging`, `development`

### Step 2: AWS SSO Authentication

Check and refresh AWS SSO session if needed:

```powershell
aws sso login --profile <profile>
```

If the user gets "Token has expired and refresh failed", run SSO login. This will open a browser for authentication.

### Step 3: Update Kubeconfig (if needed)

If the user needs to set up or update their kubeconfig for EKS:

```powershell
aws eks update-kubeconfig --name <cluster-name> --profile <profile> --region <region>
```

To list available clusters:

```powershell
aws eks list-clusters --profile <profile>
```

### Step 4: List Namespaces

Show available namespaces:

```powershell
kubectl get namespaces
```

Ask the user which namespace they want to work in.

### Step 5: List Pods

List pods in the selected namespace:

```powershell
kubectl get pods -n <namespace>
```

Help the user identify the pod they want to access. Pods have naming patterns like:
- `<deployment-name>-<replicaset-hash>-<pod-hash>` (e.g., `enginelinux-d46c468d8-5vhv7`)

Filter by status if needed:

```powershell
# Only running pods
kubectl get pods -n <namespace> --field-selector=status.phase=Running
```

### Step 6: Exec Into Pod

Open an interactive shell in the pod:

```powershell
kubectl exec -it <pod-name> -n <namespace> -- /bin/bash
```

If bash is not available, try:

```powershell
kubectl exec -it <pod-name> -n <namespace> -- /bin/sh
```

For multi-container pods, specify the container:

```powershell
kubectl exec -it <pod-name> -n <namespace> -c <container-name> -- /bin/bash
```

## Quick Reference

| Task | Command |
|------|---------|
| SSO Login | `aws sso login --profile <profile>` |
| List clusters | `aws eks list-clusters --profile <profile>` |
| Update kubeconfig | `aws eks update-kubeconfig --name <cluster> --profile <profile>` |
| List namespaces | `kubectl get namespaces` |
| List pods | `kubectl get pods -n <namespace>` |
| Exec into pod | `kubectl exec -it <pod> -n <namespace> -- /bin/bash` |
| Get pod logs | `kubectl logs <pod> -n <namespace>` |
| Describe pod | `kubectl describe pod <pod> -n <namespace>` |

## Troubleshooting

### Token Expired
```
Error when retrieving token from sso: Token has expired and refresh failed
```
Solution: Run `aws sso login --profile <profile>`

### Context Not Found
```
error: failed to switch context: no context exists with the name
```
Solution: Run `aws eks update-kubeconfig` to set up the context

### Pod Not Running
If pod status shows `ContainerCreating`, `Error`, or `CrashLoopBackOff`:
- Check events: `kubectl describe pod <pod> -n <namespace>`
- Check logs: `kubectl logs <pod> -n <namespace>`

### Permission Denied in Pod
Some pods run as non-root users with limited access. The working directory after exec may be the application directory.
