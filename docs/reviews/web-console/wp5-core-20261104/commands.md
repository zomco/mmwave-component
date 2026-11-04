# 实际命令

日期：2026-11-04。工作目录：submodules/mmwave-component/static。

## 先跑新增测试

node --test --test-timeout=120000 test/browser/app-flash-ready.test.js

退出码 0。TAP 汇总：tests 2，pass 2，fail 0，duration_ms 20910.616。

- a checked Beta manifest can flash only while the port is free：duration_ms 18712.9093
- a bad manifest checksum keeps flashing disabled：duration_ms 2042.0491

## 然后各跑一次

单元测试只在该进程里把 D:/msys64/ucrt64/bin 加到 PATH，并设置 MWCP_GPP 为该目录下的 g++.exe，结束后恢复。没有写进生产代码。

npm.cmd run test:unit
npm.cmd run test:browser
npm.cmd run build

| 脚本 | 退出码 | 观察到的汇总 |
| --- | --- | --- |
| test:unit | 0 | tests 137，pass 137，fail 0，duration_ms 17137.7179 |
| test:browser | 0 | tests 6，pass 6，fail 0，duration_ms 13286.0611 |
| build | 0 | Vite 8.3.4，built in 1.04s。另有 lucide-react use client 警告 |

浏览器 6 条的名称是：

- production app connects, saves, and keeps one port owner
- a checked Beta manifest can flash only while the port is free
- a bad manifest checksum keeps flashing disabled
- browser page clicks config and shows stale data on the simulated console
- browser bundle instantiates ProtocolClient without Node APIs
- invalid browser path fails quickly and does not stay running

单元测试的工具回传从尾部开始，能直接看到的是第 135 到 137 条和最后的 1..137 汇总。没有把没回传的前半段补写进来。

这些命令之后没有再改产品代码或测试，因此没有重跑。
