# nftables 端口转发管理工具

通过交互菜单管理 IPv4 端口转发，并可定时解析域名以更新转发目标。

## 功能

- 添加、查看、删除和修改 TCP + UDP 转发。菜单选择 **7 修改转发目标**，选择现有规则后输入新的目标 IPv4、端口；留空保留原值。加载失败时尝试恢复先前配置。
- 可选的域名更新工具，每 5 分钟解析绑定到本机端口的域名，并在 IPv4 变化后更新 NAT 规则。详细步骤见 [域名更新说明](域名更新说明.md)。
- 新版菜单和更新程序共享一把锁，避免双方同时更改转发配置。旧版脚本和其他手工修改不受此锁保护。

## 使用

需要具备 root 权限的 Linux、Bash、nftables、systemd 和 `flock`（通常来自 util-linux）。域名自动更新另需 Python 3 和 `getent`。克隆项目或下载文件后：

```bash
git clone https://github.com/ZikQ-Shmily/nftables-port-forward.git && cd nftables-port-forward && sudo bash nftables.sh
```

系统初始化提示：**选择安装并确认时可能清空整个 nftables 规则集，重命名已有配置并更改内核设置。** 请先检查现有防火墙和备份，尤其是在通过 SSH 远程管理的服务器上。脚本可能同时修改 UFW、iptables 或 firewalld 配置。

## 域名与防火墙

先使用主菜单添加一条以当前 IPv4 为目标的规则，再依照 [域名更新说明](域名更新说明.md) 配置端口和域名映射并启用定时器。域名更新器更新本工具的 NAT 规则，**不会更新其他防火墙中的 FORWARD 放行规则**。如果其放行规则限定旧目标 IP，DNS 更新后可能无法连接；需事先由管理员设置适当的过滤规则。

一个域名只使用一个 IPv4；现用 IP 仍在解析结果中时优先保留。DNS 查询失败保留旧值。已建立的连接可能继续使用旧 IP。域名映射按本机端口关联：使用菜单修改了目标 IP 后，定时器仍可能将其改回域名解析的 IP；需要固定 IP 时，请从 `/etc/nftables.d/domain-targets.json` 删除对应映射。删除转发后也应删除映射。仅支持本工具生成的规则格式。

## 测试

```bash
bash -n nftables.sh
bash test_edit.sh
python3 test_update.py
```

测试使用模拟环境，不会修改防火墙；生产使用前请在独立 Linux 测试环境验证系统防火墙、网络路径和持久化行为。
