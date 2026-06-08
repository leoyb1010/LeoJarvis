import Foundation
import Darwin
import Network
import Security

#if os(iOS)
import UIKit
#endif

#if canImport(Citadel)
import Citadel
#endif

#if canImport(NIOCore)
import NIOCore
#endif

enum FleetError: LocalizedError {
    case missingPassword
    case missingBridgeToken
    case invalidBridgeURL
    case bridgeUnavailable(String)
    case cloudflareAccessUnsupported(String)
    case sshPortUnavailable(String)
    case sshUnavailable
    case invalidProbeOutput
    case keychain(String)

    var errorDescription: String? {
        switch self {
        case .missingPassword:
            return "没有保存 SSH 密码。"
        case .missingBridgeToken:
            return "没有保存 Mac mini Bridge token。"
        case .invalidBridgeURL:
            return "Mac mini Bridge 地址无效。"
        case let .bridgeUnavailable(message):
            return "Mac mini Bridge 不可用：\(message)"
        case let .cloudflareAccessUnsupported(host):
            return "\(host) 是 Cloudflare Access SSH。iOS App 不能直接运行 cloudflared ProxyCommand；请改用 Tailscale 或局域网可直连地址。"
        case let .sshPortUnavailable(message):
            return message
        case .sshUnavailable:
            return "SSH 包依赖尚未解析。请用完整 Xcode 打开工程并拉取 Swift Package。"
        case .invalidProbeOutput:
            return "远端探测输出不是有效 JSON。"
        case let .keychain(message):
            return "Keychain 错误：\(message)"
        }
    }
}

enum BridgeDiagnostics {
    private static let formatter = ISO8601DateFormatter()

    static func record(_ message: String) {
        do {
            let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first
            guard let url = directory?.appendingPathComponent("bridge-diagnostics.log") else { return }
            let line = "\(formatter.string(from: Date())) \(message)\n"
            let data = Data(line.utf8)
            if FileManager.default.fileExists(atPath: url.path) {
                let handle = try FileHandle(forWritingTo: url)
                try handle.seekToEnd()
                try handle.write(contentsOf: data)
                try handle.close()
            } else {
                try data.write(to: url, options: .atomic)
            }
        } catch {
            // Diagnostics must never affect app behavior.
        }
    }
}

enum LocalNetworkPermissionProbe {
    private static var browser: NWBrowser?

    static func trigger() {
        #if os(iOS)
        guard browser == nil else { return }
        let descriptor = NWBrowser.Descriptor.bonjour(type: "_http._tcp", domain: nil)
        let next = NWBrowser(for: descriptor, using: .tcp)
        browser = next
        BridgeDiagnostics.record("local-network-probe start")
        next.stateUpdateHandler = { state in
            BridgeDiagnostics.record("local-network-probe state=\(state)")
        }
        next.start(queue: .global(qos: .utility))
        DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + 2.5) {
            next.cancel()
            if let current = browser, current === next {
                browser = nil
            }
            BridgeDiagnostics.record("local-network-probe stop")
        }
        #endif
    }
}

final class KeychainVault {
    private let service = "com.leo.cortexfleet.ssh-password"
    private let bridgeService = "com.leo.cortexfleet.mobile-bridge"
    private let bridgeAccount = "mac-mini-bridge-token"

    func savePassword(_ password: String, for hostID: String) throws {
        let data = Data(password.utf8)
        var query = baseQuery(for: hostID)
        SecItemDelete(query as CFDictionary)
        query[kSecValueData as String] = data
        query[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        let status = SecItemAdd(query as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw FleetError.keychain(status.description)
        }
    }

    func password(for hostID: String) throws -> String {
        var query = baseQuery(for: hostID)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess, let data = item as? Data, let password = String(data: data, encoding: .utf8) else {
            throw FleetError.missingPassword
        }
        return password
    }

    func deletePassword(for hostID: String) {
        SecItemDelete(baseQuery(for: hostID) as CFDictionary)
    }

    func saveBridgeToken(_ token: String) throws {
        let data = Data(token.utf8)
        var query = bridgeQuery()
        SecItemDelete(query as CFDictionary)
        query[kSecValueData as String] = data
        query[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        let status = SecItemAdd(query as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw FleetError.keychain(status.description)
        }
    }

    func bridgeToken() throws -> String {
        var query = bridgeQuery()
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess, let data = item as? Data, let token = String(data: data, encoding: .utf8), !token.isEmpty else {
            throw FleetError.missingBridgeToken
        }
        return token
    }

    func hasBridgeToken() -> Bool {
        (try? bridgeToken().isEmpty == false) ?? false
    }

    private func baseQuery(for hostID: String) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: hostID
        ]
    }

    private func bridgeQuery() -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: bridgeService,
            kSecAttrAccount as String: bridgeAccount
        ]
    }
}

struct LocalDeviceProbe {
    static func snapshot() -> LocalDeviceSnapshot {
        let storage = storageStats()
        return LocalDeviceSnapshot(
            name: deviceName,
            model: modelName,
            modelIdentifier: modelIdentifier,
            systemVersion: systemVersion,
            osBuild: osBuild,
            batteryPercent: batteryPercent,
            batteryState: batteryState,
            batteryHealth: "系统未开放",
            batteryHealthDetail: "最大容量/循环次数不可读",
            storageTotalGB: storage.total,
            storageFreeGB: storage.importantFree,
            storageAvailableOpportunisticGB: storage.opportunisticFree,
            memoryTotalGB: Double(ProcessInfo.processInfo.physicalMemory) / 1_073_741_824,
            processorCount: ProcessInfo.processInfo.processorCount,
            activeProcessorCount: ProcessInfo.processInfo.activeProcessorCount,
            thermalState: thermalState,
            lowPowerMode: ProcessInfo.processInfo.isLowPowerModeEnabled,
            uptimeHours: ProcessInfo.processInfo.systemUptime / 3600,
            screenDescription: screenDescription,
            screenScale: screenScale,
            maxFramesPerSecond: maxFramesPerSecond,
            interfaceIdiom: interfaceIdiom,
            localeIdentifier: Locale.current.identifier,
            timeZoneIdentifier: TimeZone.current.identifier,
            collectedAt: Date()
        )
    }

    private static var deviceName: String {
        #if os(iOS)
        UIDevice.current.isBatteryMonitoringEnabled = true
        return UIDevice.current.name
        #else
        return Host.current().localizedName ?? "This Mac"
        #endif
    }

    private static var modelName: String {
        #if os(iOS)
        return UIDevice.current.model
        #else
        return "Mac"
        #endif
    }

    private static var modelIdentifier: String {
        var systemInfo = utsname()
        uname(&systemInfo)
        let mirror = Mirror(reflecting: systemInfo.machine)
        let bytes = mirror.children.compactMap { child -> UInt8? in
            guard let value = child.value as? Int8, value != 0 else { return nil }
            return UInt8(value)
        }
        return String(bytes: bytes, encoding: .ascii) ?? "-"
    }

    private static var systemVersion: String {
        #if os(iOS)
        return "\(UIDevice.current.systemName) \(UIDevice.current.systemVersion)"
        #else
        return ProcessInfo.processInfo.operatingSystemVersionString
        #endif
    }

    private static var osBuild: String {
        stringSysctl("kern.osversion") ?? "-"
    }

    private static var batteryPercent: Double? {
        #if os(iOS)
        UIDevice.current.isBatteryMonitoringEnabled = true
        let level = UIDevice.current.batteryLevel
        return level >= 0 ? Double(level) * 100 : nil
        #else
        return nil
        #endif
    }

    private static var batteryState: String {
        #if os(iOS)
        UIDevice.current.isBatteryMonitoringEnabled = true
        switch UIDevice.current.batteryState {
        case .charging: return "充电中"
        case .full: return "已充满"
        case .unplugged: return "电池"
        case .unknown: return "未知"
        @unknown default: return "未知"
        }
        #else
        return "-"
        #endif
    }

    private static var thermalState: String {
        switch ProcessInfo.processInfo.thermalState {
        case .nominal: return "正常"
        case .fair: return "温热"
        case .serious: return "偏热"
        case .critical: return "过热"
        @unknown default: return "未知"
        }
    }

    private static var screenDescription: String {
        #if os(iOS)
        let bounds = UIScreen.main.nativeBounds
        return "\(Int(bounds.width))×\(Int(bounds.height))"
        #else
        return "-"
        #endif
    }

    private static var screenScale: Double {
        #if os(iOS)
        return Double(UIScreen.main.nativeScale)
        #else
        return 1
        #endif
    }

    private static var maxFramesPerSecond: Int {
        #if os(iOS)
        return UIScreen.main.maximumFramesPerSecond
        #else
        return 0
        #endif
    }

    private static var interfaceIdiom: String {
        #if os(iOS)
        switch UIDevice.current.userInterfaceIdiom {
        case .phone: return "iPhone"
        case .pad: return "iPad"
        case .mac: return "Mac"
        case .tv: return "Apple TV"
        case .carPlay: return "CarPlay"
        case .vision: return "Vision"
        case .unspecified: return "未指定"
        @unknown default: return "未知"
        }
        #else
        return "Mac"
        #endif
    }

    private static func storageStats() -> (total: Double, importantFree: Double, opportunisticFree: Double) {
        do {
            let values = try URL(fileURLWithPath: NSHomeDirectory()).resourceValues(forKeys: [
                .volumeTotalCapacityKey,
                .volumeAvailableCapacityForImportantUsageKey,
                .volumeAvailableCapacityForOpportunisticUsageKey
            ])
            let total = Double(values.volumeTotalCapacity ?? 0) / 1_073_741_824
            let importantFree = Double(values.volumeAvailableCapacityForImportantUsage ?? 0) / 1_073_741_824
            let opportunisticFree = Double(values.volumeAvailableCapacityForOpportunisticUsage ?? 0) / 1_073_741_824
            return (total, importantFree, opportunisticFree)
        } catch {
            return (0, 0, 0)
        }
    }

    private static func stringSysctl(_ name: String) -> String? {
        var size = 0
        guard sysctlbyname(name, nil, &size, nil, 0) == 0, size > 0 else { return nil }
        var buffer = [CChar](repeating: 0, count: size)
        guard sysctlbyname(name, &buffer, &size, nil, 0) == 0 else { return nil }
        return String(cString: buffer)
    }
}

struct SSHProbeService {
    private let keychain: KeychainVault

    init(keychain: KeychainVault) {
        self.keychain = keychain
    }

    func probe(_ host: MonitoredHost) async -> HostSnapshot {
        guard host.enabled else {
            return .pending(for: host)
        }

        do {
            guard host.connectionKind == .direct else {
                throw FleetError.cloudflareAccessUnsupported(host.authDomain.isEmpty ? host.host : host.authDomain)
            }
            try await Self.checkSSHPort(host)
            let password = try keychain.password(for: host.id)
            return try await runSSHProbe(host: host, password: password)
        } catch FleetError.missingPassword {
            return .needsCredentials(
                for: host,
                message: "已确认 \(host.host):\(host.port) 可以连接。进入「主机」页编辑此主机，输入 SSH 密码后即可采集 CPU/RAM/磁盘状态。"
            )
        } catch {
            return .failure(for: host, error: error.localizedDescription)
        }
    }

    private static func checkSSHPort(_ host: MonitoredHost) async throws {
        guard let port = NWEndpoint.Port(rawValue: UInt16(host.port)) else {
            throw FleetError.sshPortUnavailable("SSH 端口无效：\(host.port)")
        }

        let result: Result<Void, FleetError> = await withCheckedContinuation { (continuation: CheckedContinuation<Result<Void, FleetError>, Never>) in
            let connection = NWConnection(host: NWEndpoint.Host(host.host), port: port, using: .tcp)
            let completion = PortCheckCompletion(connection: connection, continuation: continuation)

            connection.stateUpdateHandler = { state in
                switch state {
                case .ready:
                    completion.finish(.success(()))
                case let .failed(error):
                    completion.finish(.failure(.sshPortUnavailable("SSH 端口不可达：\(error.localizedDescription)")))
                case let .waiting(error):
                    if case .posix(let code) = error, code == .ECONNREFUSED {
                        completion.finish(.failure(.sshPortUnavailable("SSH 端口被拒绝，请确认目标主机已开启远程登录。")))
                    }
                case .cancelled:
                    break
                default:
                    break
                }
            }

            connection.start(queue: .global(qos: .utility))

            Task {
                try? await Task.sleep(for: .seconds(4))
                completion.finish(.failure(.sshPortUnavailable("SSH 端口连接超时，请确认 iPhone/iPad 已登录同一个 Tailscale tailnet，或与主机在同一局域网。")))
            }
        }

        try result.get()
    }

    private func runSSHProbe(host: MonitoredHost, password: String) async throws -> HostSnapshot {
        #if canImport(Citadel)
        let settings = SSHClientSettings(
            host: host.host,
            port: host.port,
            authenticationMethod: {
                .passwordBased(username: host.username, password: password)
            },
            hostKeyValidator: .acceptAnything()
        )
        let client = try await SSHClient.connect(to: settings)
        do {
            let buffer = try await client.executeCommand(Self.probeCommand, maxResponseSize: 96 * 1024)
            try? await client.close()
            let output = Self.string(from: buffer)
            return try Self.snapshot(from: output, host: host)
        } catch {
            try? await client.close()
            throw error
        }
        #else
        throw FleetError.sshUnavailable
        #endif
    }

    #if canImport(Citadel)
    private static func string(from buffer: ByteBuffer) -> String {
        var copy = buffer
        return copy.readString(length: copy.readableBytes) ?? ""
    }
    #endif

    private static func snapshot(from output: String, host: MonitoredHost) throws -> HostSnapshot {
        guard let line = output.split(separator: "\n").last,
              let data = String(line).data(using: .utf8) else {
            throw FleetError.invalidProbeOutput
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let payload = try decoder.decode(RemoteProbePayload.self, from: data)
        return HostSnapshot(
            id: host.id,
            hostID: host.id,
            name: host.title,
            address: host.addressLine,
            isOnline: true,
            health: payload.health,
            status: payload.status,
            os: payload.os,
            model: payload.model,
            metrics: payload.metrics,
            services: payload.services,
            cliTools: payload.modules.cliTools,
            topProcesses: payload.modules.topProcesses,
            risks: payload.risks.map { HealthRisk(title: $0.title, advice: $0.advice, level: $0.level) },
            privacy: payload.privacy,
            collectedAt: Date(timeIntervalSince1970: TimeInterval(payload.generatedAt)),
            error: nil
        )
    }

    private static let probeCommand = "python3 - <<'PY'\n\(probeScript)\nPY"

    private static let probeScript = #"""
import json, os, platform, re, shutil, socket, subprocess, time

def run(cmd, timeout=5):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception:
        return ""

def first_line(text):
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line[:100]
    return ""

def is_number(value):
    try:
        float(value)
        return True
    except Exception:
        return False

host = socket.gethostname().split('.')[0]
system = platform.system()

try:
    l1, l5, l15 = os.getloadavg()
except Exception:
    l1 = l5 = l15 = 0.0
cores = os.cpu_count() or 1
load_pct = round(l1 / max(1, cores) * 100, 1)

try:
    total, used, free = shutil.disk_usage('/')
    disk_pct = round(used / total * 100, 1)
except Exception:
    free = 0
    disk_pct = 0

ram_total = ram_used = 0.0
ram_pct = None
try:
    if system == 'Linux':
        info = {}
        for line in open('/proc/meminfo'):
            k, _, v = line.partition(':')
            info[k.strip()] = float(v.strip().split()[0]) * 1024
        ram_total = info.get('MemTotal', 0)
        avail = info.get('MemAvailable', info.get('MemFree', 0))
        ram_used = max(0.0, ram_total - avail)
    elif system == 'Darwin':
        ram_total = float(run(['sysctl', '-n', 'hw.memsize']) or 0)
        page = 4096
        vm = run(['vm_stat'])
        free_pages = 0
        for line in vm.splitlines():
            if 'page size of' in line:
                nums = [int(s) for s in line.split() if s.isdigit()]
                if nums:
                    page = nums[0]
            if line.startswith('Pages free') or line.startswith('Pages speculative'):
                free_pages += int(''.join(ch for ch in line.split(':')[1] if ch.isdigit()) or 0)
        ram_used = max(0.0, ram_total - free_pages * page)
    if ram_total > 0:
        ram_pct = round(ram_used / ram_total * 100, 1)
except Exception:
    pass

uptime_h = None
try:
    if system == 'Linux':
        uptime_h = round(float(open('/proc/uptime').read().split()[0]) / 3600, 1)
    elif system == 'Darwin':
        bt = run(['sysctl', '-n', 'kern.boottime'])
        m = re.search(r'sec\s*=\s*(\d+)', bt)
        if m:
            uptime_h = round((time.time() - int(m.group(1))) / 3600, 1)
except Exception:
    pass

ps_text = run(['ps', '-axo', 'pid,pcpu,pmem,comm,args'], timeout=6)
ps_lines = [line for line in ps_text.splitlines()[1:] if line.strip()]
ps_lower = "\n".join(ps_lines).lower()

def has_process(patterns):
    return any(pattern.lower() in ps_lower for pattern in patterns)

def process_detail(patterns):
    for line in ps_lines:
        lower = line.lower()
        if any(pattern.lower() in lower for pattern in patterns):
            parts = line.split(None, 4)
            if len(parts) >= 4:
                pid = parts[0]
                name = os.path.basename(parts[3])
                return "pid %s · %s" % (pid, name[:42])
    return ""

service_items = []
seen_services = set()

def add_service(name, kind, running, detail="", port=None, status=None):
    key = "%s:%s:%s" % (kind, name, port or "")
    if key in seen_services:
        return
    seen_services.add(key)
    service_items.append({
        'name': name[:80],
        'kind': kind,
        'status': status or ('运行' if running else '停止'),
        'is_running': bool(running),
        'detail': (detail or "")[:120],
        'port': port,
    })

ports = [
    ('SSH', 22),
    ('HTTP', 80),
    ('HTTPS', 443),
    ('Web 3000', 3000),
    ('Vite 5173', 5173),
    ('API 8080', 8080),
    ('LeoJarvis', 8787),
    ('Ollama', 11434),
    ('PostgreSQL', 5432),
    ('MySQL', 3306),
    ('Redis', 6379),
    ('MongoDB', 27017),
]
for name, port in ports:
    ok = False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.45)
            ok = s.connect_ex(('127.0.0.1', port)) == 0
    except Exception:
        ok = False
    add_service(name, '端口', ok, '127.0.0.1:%d' % port, port=port)

process_services = [
    ('Tailscale', ['tailscale', 'ipnextension']),
    ('Cloudflare Tunnel', ['cloudflared']),
    ('Docker Desktop', ['com.docker', 'docker desktop']),
    ('Ollama', ['ollama']),
    ('PostgreSQL', ['postgres']),
    ('Redis', ['redis-server']),
    ('MySQL', ['mysqld']),
    ('MongoDB', ['mongod']),
    ('Nginx', ['nginx']),
    ('Caddy', ['caddy']),
    ('Node/Web', ['node ', '/node', ' vite', ' next', 'npm ']),
    ('Codex', ['codex']),
]
for name, patterns in process_services:
    running = has_process(patterns)
    if running:
        add_service(name, '进程', True, process_detail(patterns))

brew = shutil.which('brew')
if brew:
    brew_out = run([brew, 'services', 'list'], timeout=7)
    for line in brew_out.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        name, status = parts[0], parts[1]
        running = status.lower().startswith('started')
        add_service(name, 'brew', running, " ".join(parts[1:])[:120], status='运行' if running else status)

if system == 'Darwin':
    launch_out = run(['launchctl', 'list'], timeout=6)
    keys = ['tailscale', 'cloudflare', 'cloudflared', 'docker', 'ollama', 'postgres', 'redis', 'mysql', 'mongo', 'nginx', 'caddy', 'codex', 'homebrew']
    for line in launch_out.splitlines()[1:]:
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        pid, code, label = parts
        lower = label.lower()
        if not any(k in lower for k in keys):
            continue
        running = pid != '-'
        detail = 'pid %s' % pid if running else 'exit/status %s' % code
        add_service(label, 'launchd', running, detail, status='运行' if running else '停止')

top = []
try:
    rows = [r.split(None, 4) for r in ps_lines]
    rows = [r for r in rows if len(r) >= 4]
    rows.sort(key=lambda r: float(r[1]) if is_number(r[1]) else 0, reverse=True)
    for r in rows[:8]:
        command = os.path.basename(r[3])[:48]
        top.append({'pid': r[0], 'cpu': r[1], 'mem': r[2], 'command': command})
except Exception:
    pass

def cli_status(label, executable, version_args=None, process_patterns=None):
    path = shutil.which(executable)
    patterns = process_patterns or [executable]
    running = has_process(patterns)
    if not path:
        return {
            'name': label,
            'status': '未安装',
            'is_available': False,
            'is_running': running,
            'version': None,
            'path': None,
            'detail': 'PATH 中未找到 %s' % executable,
        }
    output = run(version_args or [path, '--version'], timeout=5)
    version = first_line(output)
    return {
        'name': label,
        'status': '运行中' if running else '可用',
        'is_available': True,
        'is_running': running,
        'version': version or None,
        'path': path,
        'detail': process_detail(patterns) if running else path,
    }

cli_defs = [
    ('Xcode', 'xcodebuild', ['xcodebuild', '-version'], ['xcodebuild', 'xcodebuildbuildservice']),
    ('Swift', 'swift', ['swift', '--version'], ['swift-frontend', 'swiftc', 'swift ']),
    ('Git', 'git', ['git', '--version'], [' git ']),
    ('Node.js', 'node', ['node', '--version'], ['node ', '/node']),
    ('npm', 'npm', ['npm', '--version'], ['npm ']),
    ('Python 3', 'python3', ['python3', '--version'], ['python3']),
    ('uv', 'uv', ['uv', '--version'], [' uv ']),
    ('Docker', 'docker', ['docker', '--version'], ['com.docker', 'docker ']),
    ('Homebrew', 'brew', ['brew', '--version'], ['brew services']),
    ('Tailscale', 'tailscale', ['tailscale', 'version'], ['tailscale', 'ipnextension']),
    ('cloudflared', 'cloudflared', ['cloudflared', '--version'], ['cloudflared']),
    ('GitHub CLI', 'gh', ['gh', '--version'], [' gh ']),
    ('Codex CLI', 'codex', ['codex', '--version'], ['codex']),
    ('Ollama', 'ollama', ['ollama', '--version'], ['ollama']),
]
cli_tools = [cli_status(*item) for item in cli_defs]

health = 100
risks = []
if disk_pct >= 92:
    health -= 24; risks.append({'title': '磁盘空间紧张', 'advice': '清理缓存、下载和大型项目。', 'level': '异常'})
elif disk_pct >= 82:
    health -= 10; risks.append({'title': '磁盘接近高水位', 'advice': '建议保持 20% 以上空闲空间。', 'level': '注意'})
if load_pct >= 120:
    health -= 18; risks.append({'title': 'CPU 负载偏高', 'advice': '检查构建任务或高占用进程。', 'level': '异常'})
elif load_pct >= 80:
    health -= 8; risks.append({'title': 'CPU 负载需观察', 'advice': '如持续偏高，查看 top 进程。', 'level': '注意'})
if ram_pct is not None and ram_pct >= 90:
    health -= 12; risks.append({'title': '内存吃紧', 'advice': '关闭占用内存较大的进程。', 'level': '注意'})

svc_online = sum(1 for s in service_items if s.get('is_running'))
print(json.dumps({
    'generated_at': int(time.time()),
    'health': max(0, health),
    'status': '异常' if any(r['level'] == '异常' for r in risks) else '注意' if risks else '健康',
    'os': platform.platform()[:90],
    'model': platform.machine(),
    'metrics': {
        'cpu_load': round(l1, 2), 'cpu_load_pct': load_pct, 'cpu_cores': cores,
        'disk_used_pct': disk_pct, 'disk_free_gb': round(free / (1024**3), 1),
        'ram_total_gb': round(ram_total / (1024**3), 1) if ram_total else None,
        'ram_used_gb': round(ram_used / (1024**3), 1) if ram_total else None,
        'ram_used_pct': ram_pct,
        'uptime_hours': uptime_h,
    },
    'modules': {'top_processes': top, 'cli_tools': cli_tools},
    'services': {'online': svc_online, 'total': len(service_items), 'items': service_items},
    'risks': risks,
    'privacy': '通过 iOS App 直连 SSH，只采集健康摘要、服务状态、CLI 状态和进程摘要，不读取项目文件内容。'
}, ensure_ascii=False))
"""#
}

struct BridgeFleetResult {
    let bridgeName: String
    let hosts: [MonitoredHost]
    let snapshots: [HostSnapshot]
}

struct MobileBridgeClient {
    func probe(settings: BridgeSettings, token: String) async throws -> BridgeFleetResult {
        guard settings.isUsable, let url = URL(string: settings.normalizedBaseURL + "/mobile/bridge/probe") else {
            throw FleetError.invalidBridgeURL
        }

        BridgeDiagnostics.record("probe request url=\(url.absoluteString)")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 24
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                BridgeDiagnostics.record("probe failed no-http-response")
                throw FleetError.bridgeUnavailable("没有收到 HTTP 响应。")
            }
            BridgeDiagnostics.record("probe response status=\(http.statusCode) bytes=\(data.count)")
            guard (200..<300).contains(http.statusCode) else {
                let message = String(data: data, encoding: .utf8) ?? "HTTP \(http.statusCode)"
                BridgeDiagnostics.record("probe failed http=\(http.statusCode) message=\(message.prefix(160))")
                throw FleetError.bridgeUnavailable(message)
            }

            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            let payload = try decoder.decode(MobileBridgeProbeResponse.self, from: data)
            BridgeDiagnostics.record("probe decoded hosts=\(payload.hosts.count) results=\(payload.results.count) online=\(payload.results.filter(\.ok).count)")
            let hosts = payload.hosts.map(\.monitoredHost)
            let hostByID = Dictionary(uniqueKeysWithValues: hosts.map { ($0.id, $0) })
            let snapshots = payload.results.map { result in
                let host = hostByID[result.device.hostID] ?? result.device.fallbackHost
                return result.device.snapshot(host: host, ok: result.ok, error: result.error)
            }
            return BridgeFleetResult(
                bridgeName: payload.bridge?.name ?? settings.name,
                hosts: hosts,
                snapshots: snapshots
            )
        } catch let error as FleetError {
            BridgeDiagnostics.record("probe fleet-error=\(error.localizedDescription)")
            throw error
        } catch {
            BridgeDiagnostics.record("probe error=\(error.localizedDescription)")
            throw FleetError.bridgeUnavailable(error.localizedDescription)
        }
    }

    func loadOverview(settings: BridgeSettings, token: String) async throws -> JarvisOverview {
        let payload: JarvisOverviewResponse = try await send(
            settings: settings,
            token: token,
            path: "/mobile/jarvis/overview",
            method: "GET",
            timeout: 18
        )
        return payload.overview
    }

    func loadNotes(settings: BridgeSettings, token: String) async throws -> MobileNotesResponse {
        try await send(
            settings: settings,
            token: token,
            path: "/mobile/jarvis/notes",
            method: "GET",
            timeout: 14
        )
    }

    func loadBriefing(settings: BridgeSettings, token: String) async throws -> MobileBriefingPayload {
        let payload: JarvisBriefingResponse = try await send(
            settings: settings,
            token: token,
            path: "/mobile/jarvis/briefing/today",
            method: "GET",
            timeout: 18
        )
        return payload.briefing
    }

    func createNote(
        settings: BridgeSettings,
        token: String,
        title: String,
        content: String,
        tags: [String],
        projectName: String
    ) async throws -> MobileNote {
        let body: [String: Any] = [
            "title": title,
            "content": content,
            "tags": tags,
            "project_name": projectName,
        ]
        let payload: JarvisNoteCreateResponse = try await send(
            settings: settings,
            token: token,
            path: "/mobile/jarvis/notes",
            method: "POST",
            body: try JSONSerialization.data(withJSONObject: body),
            timeout: 16
        )
        return payload.note
    }

    private func send<T: Decodable>(
        settings: BridgeSettings,
        token: String,
        path: String,
        method: String,
        body: Data? = nil,
        timeout: TimeInterval
    ) async throws -> T {
        guard settings.isUsable, let url = URL(string: settings.normalizedBaseURL + path) else {
            throw FleetError.invalidBridgeURL
        }

        BridgeDiagnostics.record("send request path=\(path) url=\(url.absoluteString)")
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = timeout
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                BridgeDiagnostics.record("send failed path=\(path) no-http-response")
                throw FleetError.bridgeUnavailable("没有收到 HTTP 响应。")
            }
            BridgeDiagnostics.record("send response path=\(path) status=\(http.statusCode) bytes=\(data.count)")
            guard (200..<300).contains(http.statusCode) else {
                let message = String(data: data, encoding: .utf8) ?? "HTTP \(http.statusCode)"
                BridgeDiagnostics.record("send failed path=\(path) http=\(http.statusCode) message=\(message.prefix(160))")
                throw FleetError.bridgeUnavailable(message)
            }
            do {
                let decoder = JSONDecoder()
                decoder.keyDecodingStrategy = .convertFromSnakeCase
                return try decoder.decode(T.self, from: data)
            } catch {
                BridgeDiagnostics.record("send decode-error path=\(path) error=\(error.localizedDescription)")
                throw error
            }
        } catch let error as FleetError {
            BridgeDiagnostics.record("send fleet-error path=\(path) error=\(error.localizedDescription)")
            throw error
        } catch {
            BridgeDiagnostics.record("send error path=\(path) error=\(error.localizedDescription)")
            throw FleetError.bridgeUnavailable(error.localizedDescription)
        }
    }
}

private struct JarvisOverviewResponse: Decodable {
    let overview: JarvisOverview
}

private struct JarvisBriefingResponse: Decodable {
    let briefing: MobileBriefingPayload
}

private struct JarvisNoteCreateResponse: Decodable {
    let note: MobileNote
}

private struct MobileBridgeProbeResponse: Decodable {
    struct Bridge: Decodable {
        let name: String
        let addresses: [String]?
        let port: Int?
    }

    let bridge: Bridge?
    let hosts: [MobileBridgeHost]
    let results: [MobileBridgeProbeResult]
}

private struct MobileBridgeHost: Decodable {
    let id: String
    let name: String
    let host: String
    let port: Int
    let username: String
    let enabled: Bool

    var monitoredHost: MonitoredHost {
        MonitoredHost(
            id: id,
            name: name,
            host: host,
            port: port,
            username: username,
            enabled: enabled,
            connectionKind: .direct
        )
    }
}

private struct MobileBridgeProbeResult: Decodable {
    let ok: Bool
    let device: MobileBridgeDevice
    let error: String?
}

private struct MobileBridgeDevice: Decodable {
    struct RiskPayload: Decodable {
        let title: String
        let advice: String
        let level: HealthRisk.Level
    }

    let hostID: String
    let deviceName: String
    let hostName: String
    let address: String?
    let generatedAt: Int
    let health: Double
    let status: String
    let os: String
    let model: String
    let metrics: HostMetrics
    let modules: RemoteProbePayload.Modules
    let services: HostServices
    let risks: [RiskPayload]
    let privacy: String

    enum CodingKeys: String, CodingKey {
        case hostID = "hostId"
        case deviceName
        case hostName
        case address
        case generatedAt
        case health
        case status
        case os
        case model
        case metrics
        case modules
        case services
        case risks
        case privacy
    }

    var fallbackHost: MonitoredHost {
        MonitoredHost(
            id: hostID,
            name: deviceName,
            host: hostName,
            port: 22,
            username: "",
            enabled: true
        )
    }

    func snapshot(host: MonitoredHost, ok: Bool, error: String?) -> HostSnapshot {
        HostSnapshot(
            id: hostID,
            hostID: hostID,
            name: deviceName.isEmpty ? host.title : deviceName,
            address: address ?? host.addressLine,
            isOnline: ok,
            health: ok ? health : 0,
            status: ok ? status : "离线",
            os: os,
            model: model,
            metrics: ok ? metrics : .empty,
            services: ok ? services : .empty,
            cliTools: ok ? modules.cliTools : [],
            topProcesses: ok ? modules.topProcesses : [],
            risks: risks.map { HealthRisk(title: $0.title, advice: $0.advice, level: $0.level) },
            privacy: privacy,
            collectedAt: ok ? Date(timeIntervalSince1970: TimeInterval(generatedAt)) : nil,
            error: error
        )
    }
}

private final class PortCheckCompletion: @unchecked Sendable {
    private let lock = NSLock()
    private var didResume = false
    private let connection: NWConnection
    private let continuation: CheckedContinuation<Result<Void, FleetError>, Never>

    init(connection: NWConnection, continuation: CheckedContinuation<Result<Void, FleetError>, Never>) {
        self.connection = connection
        self.continuation = continuation
    }

    func finish(_ result: Result<Void, FleetError>) {
        lock.lock()
        guard !didResume else {
            lock.unlock()
            return
        }
        didResume = true
        lock.unlock()
        connection.cancel()
        continuation.resume(returning: result)
    }
}

private struct RemoteProbePayload: Decodable {
    struct Modules: Decodable {
        var topProcesses: [HostProcess] = []
        var cliTools: [HostCLIStatus] = []

        enum CodingKeys: String, CodingKey {
            case topProcesses
            case cliTools
        }

        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            topProcesses = try c.decodeIfPresent([HostProcess].self, forKey: .topProcesses) ?? []
            cliTools = try c.decodeIfPresent([HostCLIStatus].self, forKey: .cliTools) ?? []
        }
    }

    struct RiskPayload: Decodable {
        let title: String
        let advice: String
        let level: HealthRisk.Level
    }

    let generatedAt: Int
    let health: Double
    let status: String
    let os: String
    let model: String
    let metrics: HostMetrics
    let modules: Modules
    let services: HostServices
    let risks: [RiskPayload]
    let privacy: String
}
