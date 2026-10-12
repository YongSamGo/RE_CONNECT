"""CycloneDX JSON SBOM을 NTIA 최소요건 7개 + NIS-SBOM 기본항목 기준으로 점검한다.
사용: python3 -I sbom_check.py sbom.json"""
import json, sys

STRONG = {"SHA-256", "SHA-384", "SHA-512", "SHA3-256", "SHA3-384", "SHA3-512",
          "BLAKE2b-256", "BLAKE2b-384", "BLAKE2b-512", "BLAKE3"}

def main(path):
    with open(path, encoding="utf-8") as f:
        bom = json.load(f)
    if bom.get("bomFormat") != "CycloneDX":
        sys.exit("CycloneDX JSON이 아님 (SPDX는 별도 확인)")
    meta = bom.get("metadata", {})
    comps = bom.get("components", [])
    deps = {d.get("ref"): d.get("dependsOn", []) for d in bom.get("dependencies", [])}
    tools = meta.get("tools", [])
    if isinstance(tools, dict):  # CycloneDX 1.5+
        tools = tools.get("components", []) + tools.get("services", [])
    tool_names = [t.get("name") for t in tools if isinstance(t, dict)]
    doc = [
        ("SBOM Standard (NIS①)", f"CycloneDX {bom.get('specVersion')}"),
        ("CycloneDX No. (NIS③)", bom.get("serialNumber")),
        ("Timestamp (NTIA, NIS⑰)", meta.get("timestamp")),
        ("SBOM Author (NTIA, NIS⑭)", [a.get("name") for a in meta.get("authors", [])] or None),
        ("생성 도구", tool_names or None),
        ("Product Name (NIS⑥)", meta.get("component", {}).get("name")),
        ("Product Version (NIS⑦)", meta.get("component", {}).get("version")),
        ("SBOM Type (NIS②, lifecycles)", [l.get("phase") or l.get("name") for l in meta.get("lifecycles", [])] or None),
    ]
    print("## 문서 수준")
    for k, v in doc:
        print(f"- {'OK ' if v else '누락'} {k}: {v}")
    print(f"\n## 컴포넌트 수준 ({len(comps)}개)")
    seen, dup = set(), []
    for c in comps:
        key = (c.get("name", "").lower(), c.get("version"))
        if key in seen:
            dup.append(f"{key[0]}@{key[1]}")
        seen.add(key)
    print(f"- {'OK ' if not dup else '중복 ' + str(len(dup))} 같은 이름·버전 중복 (가이드라인 표18 사례)" + (f": {', '.join(dup[:10])}" if dup else ""))
    miss = {k: [] for k in ["supplier", "version", "purl/cpe", "hash", "strong-hash", "license", "dependency"]}
    for c in comps:
        name = f"{c.get('name')}@{c.get('version')}"
        if not (c.get("supplier") or c.get("publisher") or c.get("author") or c.get("authors")):
            miss["supplier"].append(name)
        if not c.get("version"):
            miss["version"].append(name)
        if not (c.get("purl") or c.get("cpe") or c.get("swid")):
            miss["purl/cpe"].append(name)
        algs = {h.get("alg") for h in c.get("hashes", [])}
        if not algs:
            miss["hash"].append(name)
        elif not algs & STRONG:
            miss["strong-hash"].append(name)
        if not c.get("licenses"):
            miss["license"].append(name)
        if c.get("bom-ref") not in deps:
            miss["dependency"].append(name)
    labels = {
        "supplier": "공급자 (NTIA, NIS⑪)", "version": "버전 (NTIA, NIS⑩)",
        "purl/cpe": "고유 식별자 PURL/CPE (NTIA, NIS⑮)", "hash": "해시 (NIS⑫)",
        "strong-hash": "SHA-256 미만 해시만 있음 (NIS⑫)", "license": "라이선스 (NIS⑱)",
        "dependency": "종속성 관계 미기재 (NTIA, NIS⑯)",
    }
    for k, names in miss.items():
        status = "OK " if not names else f"누락 {len(names)}"
        print(f"- {status} {labels[k]}" + (f": {', '.join(names[:10])}{' ...' if len(names) > 10 else ''}" if names else ""))
    vulns = bom.get("vulnerabilities", [])
    print(f"\n## 취약점 (NIS⑲⑳): {len(vulns)}건")
    for v in vulns:
        scores = [r.get("score") for r in v.get("ratings", []) if r.get("score") is not None]
        top = max(scores) if scores else None
        flag = "즉시 조치/협의 (CVSS>=7.0)" if top is not None and top >= 7.0 else ""
        affects = [a.get("ref") for a in v.get("affects", [])]
        print(f"- {v.get('id')} src={v.get('source', {}).get('name')} score={top} affects={affects} {flag}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
