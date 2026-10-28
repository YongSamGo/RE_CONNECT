"""Render one reviewed public DNS name into the Nginx configuration."""
import argparse
import ipaddress
from pathlib import Path
import re


def render(domain: str) -> str:
    # ASCII DNS labels only: no Nginx directives, variables, regexes or wildcards.
    label = r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?'
    if len(domain) > 253 or not re.fullmatch(rf'{label}(?:\.{label})+', domain):
        raise ValueError('a lowercase ASCII DNS domain is required')
    try:
        ipaddress.ip_address(domain)
    except ValueError:
        pass
    else:
        raise ValueError('a DNS domain, not an IP address, is required')
    template = Path(__file__).with_name('nginx.conf.template').read_text(encoding='utf-8')
    return template.replace('@@DOMAIN@@', domain)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        config = render(args.domain)
    except ValueError as error:
        parser.error(str(error))
    # Exclusive creation avoids replacing a reviewed/live configuration by accident.
    with args.output.open('x', encoding='utf-8', newline='\n') as destination:
        destination.write(config)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
