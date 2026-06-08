-- ============================================================================
-- HPC 计算任务历史数据库 Schema
-- 用于：收敛预估、错误模式挖掘、服务器负载分析、代算报价依据
-- ============================================================================

-- 服务器清单
CREATE TABLE IF NOT EXISTS servers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    host        TEXT NOT NULL,                  -- 主机名/IP
    port        INTEGER DEFAULT 22,
    platform    TEXT,                            -- autodl / gpushare / baremetal
    is_docker   INTEGER DEFAULT 0,              -- 0=bare, 1=docker
    mpi_type    TEXT,                            -- openmpi / mpich / intelmpi
    cpu_cores   INTEGER,
    total_mem_gb REAL,
    shm_gb      REAL,                           -- /dev/shm 大小
    notes       TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

-- 计算任务记录
CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT UNIQUE NOT NULL,        -- 全局唯一 job_id
    server_id       INTEGER REFERENCES servers(id),
    code            TEXT NOT NULL,               -- vasp / cp2k / lammps / gaussian / orca / qe
    version         TEXT,                        -- 6.4.3 / 2024.1 / etc
    work_dir        TEXT,                        -- 工作目录
    input_summary   TEXT,                        -- 体系描述（如 "Ni-111 slab 4层 真空15Å"）
    natoms          INTEGER,                     -- 原子数
    ncores          INTEGER,                     -- 使用的核数
    walltime        INTEGER,                     -- 预期墙时（秒）
    status          TEXT DEFAULT 'submitted',    -- submitted / running / completed / failed / killed
    error_type      TEXT,                        -- oom_killed / scf_diverged / ... (NULL if success)
    exit_code       INTEGER,
    actual_signal   INTEGER,
    submitted_at    TEXT DEFAULT (datetime('now')),
    started_at      TEXT,
    finished_at     TEXT,
    elapsed_sec     INTEGER,                     -- 实际运行时间（秒）
    cpu_hours       REAL,                        -- 核心·小时消耗
    peak_mem_mb     REAL,                        -- 内存峰值（MB）
    final_energy    REAL,                        -- 最终能量（eV，如有）
    scf_steps       INTEGER,                     -- 总 SCF 步数
    geo_steps       INTEGER,                     -- 几何优化步数
    notes           TEXT,

    FOREIGN KEY (server_id) REFERENCES servers(id)
);

CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_code ON jobs(code);
CREATE INDEX idx_jobs_error ON jobs(error_type);
CREATE INDEX idx_jobs_submitted ON jobs(submitted_at);
CREATE INDEX idx_jobs_server ON jobs(server_id);

-- 修复历史（Success Capture S6）
CREATE TABLE IF NOT EXISTS fixes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT NOT NULL,               -- 关联的失败任务
    error_type      TEXT NOT NULL,
    code            TEXT NOT NULL,
    fix_action      TEXT NOT NULL,               -- 执行的修复
    params_changed  TEXT,                        -- JSON: 修改的参数
    success         INTEGER DEFAULT 0,           -- 0=失败, 1=真成功, 2=巧合通过
    verified        INTEGER DEFAULT 0,           -- 是否已验证可复现
    cost            TEXT,                        -- 修复代价（计算时间/精度损失）
    notes           TEXT,
    applied_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (job_id) REFERENCES jobs(job_id)
);

CREATE INDEX idx_fixes_error ON fixes(error_type, code);
CREATE INDEX idx_fixes_success ON fixes(success);

-- SCF 收敛快照（用于收敛预估）
CREATE TABLE IF NOT EXISTS scf_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT NOT NULL,
    step            INTEGER,                     -- SCF 步序号
    energy          REAL,                        -- 当前能量
    dE              REAL,                        -- 与上步能量差
    convergence_rate REAL,                       -- -log10(dE) 斜率
    classification  TEXT,                        -- converging / diverging / oscillating / stagnating
    snapshot_at     TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (job_id) REFERENCES jobs(job_id)
);

-- 服务器健康记录
CREATE TABLE IF NOT EXISTS server_health (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id       INTEGER REFERENCES servers(id),
    cpu_load        REAL,
    mem_used_pct    REAL,
    zombie_count    INTEGER,
    compute_jobs    INTEGER,
    checked_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (server_id) REFERENCES servers(id)
);

-- ============================================================================
-- 常用分析查询
-- ============================================================================

-- 1. 过去 30 天各 error_type 分布
-- SELECT error_type, COUNT(*) as cnt FROM jobs
-- WHERE finished_at > datetime('now', '-30 days') AND status = 'failed'
-- GROUP BY error_type ORDER BY cnt DESC;

-- 2. 各服务器成功率
-- SELECT s.host, s.platform,
--   COUNT(CASE WHEN j.status = 'completed' THEN 1 END) as success,
--   COUNT(CASE WHEN j.status = 'failed' THEN 1 END) as failed,
--   ROUND(100.0 * COUNT(CASE WHEN j.status = 'completed' THEN 1 END) / COUNT(*), 1) as success_rate
-- FROM servers s JOIN jobs j ON s.id = j.server_id
-- GROUP BY s.id ORDER BY success_rate DESC;

-- 3. OOM 频发体系（相同 natoms 范围内 OOM 率 > 50%）
-- SELECT natoms, COUNT(*) as total,
--   COUNT(CASE WHEN error_type = 'oom_killed' THEN 1 END) as ooms,
--   ROUND(100.0 * COUNT(CASE WHEN error_type = 'oom_killed' THEN 1 END) / COUNT(*), 1) as oom_rate
-- FROM jobs WHERE status = 'failed'
-- GROUP BY natoms HAVING oom_rate > 50
-- ORDER BY oom_rate DESC;

-- 4. 收敛预估（同类体系平均耗时）
-- SELECT code, natoms, ncores,
--   COUNT(*) as jobs,
--   ROUND(AVG(elapsed_sec) / 3600.0, 1) as avg_hours,
--   ROUND(AVG(scf_steps), 0) as avg_scf_steps,
--   ROUND(AVG(geo_steps), 0) as avg_geo_steps
-- FROM jobs WHERE status = 'completed'
-- GROUP BY code, natoms, ncores
-- ORDER BY code, natoms;

-- 5. 真成功修复方案（Success Capture 归档）
-- SELECT f.error_type, f.code, f.fix_action, f.params_changed, COUNT(*) as times_used
-- FROM fixes f WHERE f.success = 1 AND f.verified = 1
-- GROUP BY f.error_type, f.code, f.fix_action
-- ORDER BY times_used DESC;

-- 6. 某台服务器上当前建议的并发数（基于历史 OOM 率）
-- SELECT s.host, s.total_mem_gb,
--   ROUND(AVG(j.peak_mem_mb)) as avg_peak_mem_mb,
--   CAST(s.total_mem_gb * 1024 * 0.8 / AVG(j.peak_mem_mb) AS INTEGER) as safe_concurrent_jobs
-- FROM servers s JOIN jobs j ON s.id = j.server_id
-- WHERE j.peak_mem_mb IS NOT NULL
-- GROUP BY s.id;
