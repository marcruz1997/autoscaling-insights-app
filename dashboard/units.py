"""Conversão de quantidades do Kubernetes ("250m", "1", "262144k", "200Mi") para números.

CPU sai em millicores e memória/disco em MiB, que são as unidades usadas no painel.
"""

_SUFFIXES = [
    ("Ki", 2**10), ("Mi", 2**20), ("Gi", 2**30), ("Ti", 2**40), ("Pi", 2**50),
    ("m", 1e-3), ("k", 1e3), ("M", 1e6), ("G", 1e9), ("T", 1e12), ("P", 1e15),
]

MIB = 1024 * 1024


def parse_quantity(value):
    """Converte uma quantidade para unidades base (cores, bytes). Devolve None se inválida."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for suffix, factor in _SUFFIXES:
        if text.endswith(suffix):
            try:
                return float(text[: -len(suffix)]) * factor
            except ValueError:
                return None
    try:
        return float(text)
    except ValueError:
        return None


def round1(x):
    return None if x is None else round(x, 1)


def cpu_m(value):
    """Quantidade de CPU -> millicores (inteiro arredondado)."""
    q = parse_quantity(value)
    return None if q is None else round(q * 1000)


def mem_mib(value):
    """Quantidade de memória -> MiB com uma casa decimal."""
    q = parse_quantity(value)
    return None if q is None else round(q / MIB, 1)


def resources(m):
    """Mapa {"cpu": ..., "memory": ...} da API -> {"cpu_m": ..., "mem_mib": ...} ou None."""
    if not m:
        return None
    return {"cpu_m": cpu_m(m.get("cpu")) or 0, "mem_mib": mem_mib(m.get("memory")) or 0}


def opt_resources(m):
    """Igual a resources(), mas mantém None quando o valor não foi definido (requests/limits)."""
    m = m or {}
    return {
        "cpu_m": cpu_m(m["cpu"]) if "cpu" in m else None,
        "mem_mib": mem_mib(m["memory"]) if "memory" in m else None,
    }
