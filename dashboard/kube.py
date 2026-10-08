"""Leitura (somente) de objetos do Kubernetes: deployments, VPAs, pods, nós e PVCs.

Cada função devolve dicionários simples, já no formato que a interface usa.
"""
import re
from urllib.parse import quote

from units import mem_mib, opt_resources, parse_quantity, resources, round1


class Kube:
    def __init__(self, http, api_url, exclude_ns_regex):
        self.http = http
        self.api = api_url.rstrip("/")
        self.exclude = re.compile(exclude_ns_regex)

    # ---------- deployments ----------

    def list_deployments(self):
        data = self.http.get_json(f"{self.api}/apis/apps/v1/deployments")
        out = []
        for item in data.get("items", []):
            meta, spec, status = item["metadata"], item.get("spec", {}), item.get("status", {})
            if self.exclude.match(meta["namespace"]):
                continue
            containers = spec.get("template", {}).get("spec", {}).get("containers", [])
            out.append({
                "namespace": meta["namespace"],
                "name": meta["name"],
                "containers": [c["name"] for c in containers],
                "replicas": spec.get("replicas", 1),
                "ready": status.get("readyReplicas", 0),
                "hasVPA": False,
            })
        out.sort(key=lambda d: (d["namespace"], d["name"]))
        return out

    # ---------- VPAs ----------

    def list_vpas(self):
        data = self.http.get_json(f"{self.api}/apis/autoscaling.k8s.io/v1/verticalpodautoscalers")
        out = []
        for item in data.get("items", []):
            meta, spec, status = item["metadata"], item.get("spec", {}), item.get("status", {})
            target_ref = spec.get("targetRef", {})
            vpa = {
                "namespace": meta["namespace"],
                "name": meta["name"],
                "created": meta.get("creationTimestamp", ""),
                "targetKind": target_ref.get("kind", ""),
                "targetName": target_ref.get("name", ""),
                "updateMode": spec.get("updatePolicy", {}).get("updateMode") or "Auto (padrão)",
                "containers": [],
                "conditions": [],
                "policies": [],
            }
            for rec in status.get("recommendation", {}).get("containerRecommendations", []):
                vpa["containers"].append({
                    "name": rec.get("containerName", ""),
                    "target": resources(rec.get("target")),
                    "lowerBound": resources(rec.get("lowerBound")),
                    "upperBound": resources(rec.get("upperBound")),
                    "uncappedTarget": resources(rec.get("uncappedTarget")),
                })
            for cond in status.get("conditions", []):
                vpa["conditions"].append({
                    "type": cond.get("type", ""),
                    "status": cond.get("status", ""),
                    "reason": cond.get("reason", ""),
                    "message": cond.get("message", ""),
                    "since": cond.get("lastTransitionTime", ""),
                })
            for pol in spec.get("resourcePolicy", {}).get("containerPolicies", []):
                vpa["policies"].append({
                    "container": pol.get("containerName", ""),
                    "mode": pol.get("mode", ""),
                    "controlled": pol.get("controlledResources"),
                    "values": pol.get("controlledValues", ""),
                    "minAllowed": opt_resources(pol.get("minAllowed")),
                    "maxAllowed": opt_resources(pol.get("maxAllowed")),
                })
            out.append(vpa)
        return out

    # ---------- pods ----------

    def list_deployment_pods(self, ns, deploy):
        """Pods de um deployment, identificados pelo ReplicaSet dono (<deploy>-<hash>)."""
        data = self.http.get_json(f"{self.api}/api/v1/namespaces/{quote(ns)}/pods")
        rs_re = re.compile("^" + re.escape(deploy) + r"-[a-z0-9]+$")
        out = []
        for p in data.get("items", []):
            owners = p["metadata"].get("ownerReferences", [])
            if not any(o.get("kind") == "ReplicaSet" and rs_re.match(o.get("name", "")) for o in owners):
                continue
            spec, status = p.get("spec", {}), p.get("status", {})
            pod = {
                "name": p["metadata"]["name"],
                "node": spec.get("nodeName", ""),
                "phase": status.get("phase", ""),
                "ready": any(c.get("type") == "Ready" and c.get("status") == "True" for c in status.get("conditions", [])),
                "qos": status.get("qosClass", ""),
                "started": status.get("startTime", ""),
                "podIP": status.get("podIP", ""),
                "claims": [v["persistentVolumeClaim"]["claimName"] for v in spec.get("volumes", []) if v.get("persistentVolumeClaim")],
                "containers": [],
            }
            statuses = {s["name"]: s for s in status.get("containerStatuses", [])}
            for c in spec.get("containers", []):
                res = c.get("resources", {})
                st = statuses.get(c["name"], {})
                state = st.get("state", {})
                if "running" in state:
                    state_txt = "Running"
                elif "waiting" in state:
                    state_txt = "Waiting: " + state["waiting"].get("reason", "")
                elif "terminated" in state:
                    state_txt = "Terminated: " + state["terminated"].get("reason", "")
                else:
                    state_txt = ""
                last = st.get("lastState", {}).get("terminated")
                pod["containers"].append({
                    "name": c["name"],
                    "ready": st.get("ready", False),
                    "restarts": st.get("restartCount", 0),
                    "state": state_txt,
                    "lastTermination": {
                        "reason": last.get("reason", ""),
                        "exitCode": last.get("exitCode", 0),
                        "finishedAt": last.get("finishedAt", ""),
                    } if last else None,
                    "requests": opt_resources(res.get("requests")),
                    "limits": opt_resources(res.get("limits")),
                    "cpuUse": None,
                    "memUse": None,
                })
            out.append(pod)
        out.sort(key=lambda p: p["name"])
        return out

    # ---------- nós ----------

    def list_nodes(self):
        data = self.http.get_json(f"{self.api}/api/v1/nodes")
        out = []
        for n in data.get("items", []):
            labels = n["metadata"].get("labels", {})
            spec, status = n.get("spec", {}), n.get("status", {})
            alloc = status.get("allocatable", {})
            taints = []
            for t in spec.get("taints", []):
                key = t.get("key", "") + ("=" + t["value"] if t.get("value") else "")
                taints.append(f"{key}:{t.get('effect', '')}")
            out.append({
                "name": n["metadata"]["name"],
                "roles": sorted(k.split("/", 1)[1] for k in labels if k.startswith("node-role.kubernetes.io/")),
                "ready": any(c.get("type") == "Ready" and c.get("status") == "True" for c in status.get("conditions", [])),
                "unschedulable": spec.get("unschedulable", False),
                "taints": taints,
                "zone": labels.get("topology.kubernetes.io/zone", ""),
                "instanceType": labels.get("node.kubernetes.io/instance-type", ""),
                "allocCpu_m": round1((parse_quantity(alloc.get("cpu")) or 0) * 1000),
                "allocMem_mib": mem_mib(alloc.get("memory")) or 0,
                "allocPods": int(parse_quantity(alloc.get("pods")) or 0),
                "reqCpu_m": None, "reqMem_mib": None, "useCpu_m": None, "useMem_mib": None, "pods": None,
            })
        out.sort(key=lambda n: n["name"])
        return out

    # ---------- PVCs ----------

    def list_pvcs(self, ns):
        data = self.http.get_json(f"{self.api}/api/v1/namespaces/{quote(ns)}/persistentvolumeclaims")
        out = []
        for p in data.get("items", []):
            spec, status = p.get("spec", {}), p.get("status", {})
            out.append({
                "name": p["metadata"]["name"],
                "phase": status.get("phase", ""),
                "storageClass": spec.get("storageClassName") or "",
                "accessModes": spec.get("accessModes", []),
                "capacity_mib": mem_mib(status.get("capacity", {}).get("storage")),
                "used_mib": None, "statsCapacity_mib": None, "inodesUsed": None, "inodes": None,
                "mounted": False,
            })
        out.sort(key=lambda p: p["name"])
        return out

