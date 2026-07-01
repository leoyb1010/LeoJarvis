import os
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 测试隔离（关键）：把数据目录钉到一次性 temp 目录，且必须在任何 `import leojarvis.*`
# 之前完成——config.py 在 import 期就把 DB_PATH/VECTORS_PATH 定死在 DATA_DIR 上。
# 不这么做，pytest 会直接读写生产库 ~/Library/Application Support/LeoJarvis/cortex.db：
#   ① 往真实库灌测试垃圾（已发生：曾漏进 3 条 P3 测试记忆）；
#   ② 结果随生产库状态漂移、不可复现——例如 list_pending_memories 的 LIMIT 会被
#      真实库里数百条 pending 记忆挤爆，新插入的断言对象落到窗口外，测试假性失败。
# conftest.py 由 pytest 在收集测试模块前导入，此处设置 env 能保证及时生效。
if not os.environ.get("LEOJARVIS_DATA_DIR"):
    os.environ["LEOJARVIS_DATA_DIR"] = tempfile.mkdtemp(prefix="leojarvis-test-")
