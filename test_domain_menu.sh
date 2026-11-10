#!/usr/bin/env bash
set -e
source ./nftables.sh
work=$(mktemp -d)
trap 'rm -r "$work"' EXIT
CONF_DIR="$work"
CONF_FILE="$work/port-forward.conf"
DOMAIN_MAP="$work/domain-targets.json"
BACKUP_DIR="$work"
mkdir "$work/bin"
cat > "$work/bin/getent" <<'MOCK'
#!/usr/bin/env bash
if [[ "$2" == example.com ]]; then
    printf '203.0.113.10 STREAM example.com\n'
else
    exit 2
fi
MOCK
chmod +x "$work/bin/getent"
export PATH="$work/bin:$PATH"
nft() { return 0; }
get_local_ip() { echo 10.0.0.1; }
init_conf() { [[ -f "$CONF_FILE" ]] || write_conf_file; }
enable_ip_forward() { :; }
check_port_conflict() { return 0; }
backup_conf() { :; }
log_action() { :; }
firewall_open_port() { :; }
firewall_close_port() { :; }
domain_requirements() { :; }
setup_domain_timer() { echo setup >> "$work/timer"; }
reload_rules() { return 0; }

do_add <<'INPUT'
17000
example.com
17000
y
INPUT
[[ $(domain_control get 17000) == example.com ]]
[[ $(do_list) == *'203.0.113.10:17000 (example.com)'* ]]
[[ $(cat "$work/timer") == setup ]]
# Blank target preserves the domain while changing port.
do_edit <<'INPUT'
1

18000
y
INPUT
[[ $(domain_control get 17000) == example.com ]]
[[ $(do_list) == *'203.0.113.10:18000 (example.com)'* ]]
# Choosing an IPv4 removes the old binding, avoiding later DNS overwrite.
do_edit <<'INPUT'
1
203.0.113.25

y
INPUT
[[ -z $(domain_control get 17000) ]]
[[ $(do_list) == *'203.0.113.25:18000'* ]]
# Rebind, then fail a rules reload; both old config and mapping must survive.
cp "$CONF_FILE" "$work/before.conf"
cp "$DOMAIN_MAP" "$work/before.json"
reload_rules() { return 1; }
do_edit <<'INPUT'
1
example.com

y
INPUT
cmp -s "$CONF_FILE" "$work/before.conf"
cmp -s "$DOMAIN_MAP" "$work/before.json"
reload_rules() { return 0; }
# Rebind then delete, with no stale domain mapping left behind.
do_edit <<'INPUT'
1
example.com

y
INPUT
[[ $(domain_control get 17000) == example.com ]]
do_delete <<'INPUT'
1
y
INPUT
[[ -z $(domain_control get 17000) ]]
echo 'domain add/list/edit/rollback/delete: OK'
