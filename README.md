# nftables 端口转发管理工具

通过交互菜单管理 IPv4 端口转发，并可定时解析域名以更新转发目标。

## 功能

- 添加、查看、删除和修改 TCP + UDP 转发。菜单选择 **7 修改转发目标**，选择现有规则后输入新的目标 IPv4 或域名、端口；留空保留原值。加载失败时尝试恢复先前配置。
- 添加或修改转发时可直接输入域名，自动解析 IPv4、保存绑定并尝试启用每 5 分钟更新的定时器。列表显示当前 IP 和括号内的域名。详细步骤见 [域名更新说明](域名更新说明.md)。
- 新版菜单和更新程序共享一把锁，避免双方同时更改转发配置。旧版脚本和其他手工修改不受此锁保护。

## 使用

需要具备 root 权限的 Linux、Bash、nftables、systemd 和 `flock`（通常来自 util-linux）。域名自动更新另需 Python 3 和 `getent`。克隆项目或下载文件后：

```bash
git clone https://github.com/ZikQ-Shmily/nftables-port-forward.git && cd nftables-port-forward && sudo bash nftables.sh
```

系统初始化提示：**选择安装并确认时可能清空整个 nftables 规则集，重命名已有配置并更改内核设置。** 请先检查现有防火墙和备份，尤其是在通过 SSH 远程管理的服务器上。脚本可能同时修改 UFW、iptables 或 firewalld 配置。

## 域名与防火墙

新增转发时直接输入域名即可，脚本会解析 IPv4、写入转发规则并尝试启用 systemd 定时器；如果启用失败会给出提示。选择列表可以看到 `IP:端口 (域名)`，旧版本的域名映射也会读取。修改目标为固定 IP、删除规则或清空规则时，脚本会同步更新域名映射。

已有项目目录的用户可在该目录运行 `git pull --ff-only && sudo bash nftables.sh` 更新和启动。脚本运行期间不需要选择安装功能；选择安装并确认可能清空现有规则。

一个域名只使用一个 IPv4；当前 IP 仍在解析结果中时优先保留。DNS 查询失败保留旧值，已建立的连接可能继续使用旧 IP。域名更新器更新本工具的 NAT 规则，**不会更新其他防火墙中的 FORWARD 放行规则**。如果其放行规则限定旧目标 IP，DNS 更新后可能无法连接；需事先设置适当的过滤规则。仅支持本工具生成的规则格式。

## 测试

```bash
bash -n nftables.sh
bash test_edit.sh
bash test_domain_menu.sh
python3 test_update.py
```

测试使用模拟环境，不会修改防火墙；生产使用前请在独立 Linux 测试环境验证系统防火墙、网络路径和持久化行为。
