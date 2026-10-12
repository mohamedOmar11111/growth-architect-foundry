import sqlite3
import os

def init_db(db_path='hq.db'):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. Schema Definition
    cursor.execute('''CREATE TABLE IF NOT EXISTS squads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        mandate TEXT
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS agents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        squad_id INTEGER,
        name TEXT NOT NULL,
        role TEXT,
        FOREIGN KEY (squad_id) REFERENCES squads(id)
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS squad_skills (
        squad_id INTEGER,
        skill_name TEXT NOT NULL,
        FOREIGN KEY (squad_id) REFERENCES squads(id)
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        folder_path TEXT,
        status TEXT,
        tier TEXT
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS inbound_proposals (
        proposal_id INTEGER PRIMARY KEY AUTOINCREMENT,
        dag_node TEXT,
        proposed_squad TEXT,
        payload JSON,
        risk_score REAL,
        priority INTEGER DEFAULT 3,
        status TEXT DEFAULT 'PROPOSED'
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS orchestration_queue (
        exec_id INTEGER PRIMARY KEY AUTOINCREMENT,
        proposal_id INTEGER,
        state TEXT DEFAULT 'PENDING',
        maker_status TEXT,
        checker_status TEXT,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (proposal_id) REFERENCES inbound_proposals(proposal_id)
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS telemetry_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        dag_node TEXT,
        internal_state TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS cross_pollination_log (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel TEXT,
        client_id TEXT,
        success_metric REAL,
        extracted_principle TEXT,
        portability_score REAL,
        confidence_weight REAL,
        tactic_ttl_days INTEGER,
        is_anti_pattern BOOLEAN DEFAULT FALSE,
        status TEXT DEFAULT 'LEARNED',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # 2. SEED DATA - The 11 Tactical Squads
    squads = [
        (1, 'RECON', 'Deep market intelligence, competitor audits, and trend hijacking.'),
        (2, 'STRATEGY', 'ROI modeling, financial precision, and 6-month roadmaps.'),
        (3, 'CONTENT', 'Nuclear content calendars, viral copywriting, and visual prompts.'),
        (4, 'LEAD_STRIKE', 'Signal-based targeting and automated B2B outbound sequences.'),
        (5, 'ADS_VAMPIRE', 'Ruthless media buying audits and competitor lead interception.'),
        (6, 'SEO_ONYX', 'Programmatic SEO, schema markup, and G.E.O dominance.'),
        (7, 'AGENCY_OS', 'Internal operations, process automation, and dashboard reporting.'),
        (8, 'SOCIAL_MEDIA', 'Viral reach, high-status community engagement, and algorithmic mastery.'),
        (9, 'LANDING_PAGE', 'High-conversion, Noir-aesthetic, architectural landing page design.'),
        (10, 'SIGNAL_FUSION', 'Fuse client-specific signals into revenue-strike opportunities.'),
        (11, 'LEAD_INTEL', 'Advanced lead enrichment, mutual mapping, and outreach precision.')
    ]
    cursor.executemany("INSERT OR IGNORE INTO squads (id, name, mandate) VALUES (?, ?, ?)", squads)

    # 3. SEED DATA - Specialized Agents (Expanded to 25)
    agents = [
        (1, 1, 'Market Auditor', 'Data collection'),
        (2, 1, 'Trend Hijacker', 'Strategy'),
        (3, 2, 'ROI Modeler', 'Analysis'),
        (4, 2, 'Financial Controller', 'Auditing'),
        (5, 3, 'Copywriter', 'Content'),
        (6, 3, 'Visual Designer', 'Creative'),
        (7, 4, 'Lead Sourcer', 'B2B'),
        (8, 4, 'Outbound Sequence Manager', 'Automation'),
        (9, 5, 'Media Buyer', 'Auditing'),
        (10, 5, 'Competitor Interceptor', 'Strategy'),
        (11, 6, 'Schema Architect', 'SEO'),
        (12, 6, 'Content Mapper', 'SEO'),
        (13, 7, 'Automation Engineer', 'Engineering'),
        (14, 7, 'Dashboard Manager', 'Reporting'),
        (15, 8, 'Social Media Strategist', 'Cross-Platform Allocation'),
        (16, 8, 'Twitter Engager', 'Real-Time Engagement'),
        (17, 9, 'Conversion Architect', 'Design & UX'),
        (18, 9, 'Copy Designer', 'Copy & Logic'),
        (19, 6, 'WP_Architect', 'CMS & SEO Automation'),
        (20, 11, 'Enrichment Agent', 'Data Intel'),
        (21, 11, 'Mutual Mapper', 'Network Strategy'),
        (22, 11, 'Outreach Drafter', 'Precision Copy'),
        (23, 11, 'Signal Scorer', 'Revenue Intent'),
        (24, 7, 'Self-Evaluator', 'Quality Control'),
        (25, 7, 'Session Observer', 'Continuous Learning'),
        (26, 8, 'Instagram Curator', 'Visual Content'),
        (27, 8, 'TikTok Strategist', 'Short-Form Video'),
        (28, 8, 'LinkedIn Strategist', 'B2B Authority'),
        (29, 8, 'Reddit Community Builder', 'Community Credibility')
    ]
    cursor.executemany("INSERT OR IGNORE INTO agents (id, squad_id, name, role) VALUES (?, ?, ?, ?)", agents)

    # 4. SEED DATA - Squad Skills (Logic Mapping)
    skills = [
        (1, 'seo-audit'), (1, 'competitors'), (1, 'ai-seo'),
        (2, 'marketing-ideas'), (2, 'pricing'), (2, 'launch'),
        (3, 'copywriting'), (3, 'social'), (3, 'emails'), (3, 'image-video-prompts'),
        (4, 'cold-email'), (4, 'sales-enablement'),
        (5, 'ads'), (5, 'ad-creative'), (5, 'meta-ads'),
        (6, 'programmatic-seo'), (6, 'schema'), (6, 'site-architecture'),
        (7, 'revops'), (7, 'analytics'), (7, 'agent-self-evaluation'), (7, 'continuous-learning'),
        (8, 'social'), (8, 'image'), (8, 'twitter'), (8, 'linkedin'),
        (8, 'instagram'), (8, 'tiktok'), (8, 'reddit'), (8, 'content-calendar'),
        (9, 'cro'), (9, 'onboarding'), (9, 'signup'),
        (10, 'marketing-psychology'), (10, 'ab-testing'),
        (11, 'lead-intelligence'), (11, 'prospecting')
    ]
    cursor.executemany("INSERT OR IGNORE INTO squad_skills (squad_id, skill_name) VALUES (?, ?)", skills)
    
    conn.commit()
    conn.close()
    print(f"Growth Architect Brain (Full Roster v2) initialized at {db_path}")

if __name__ == "__main__":
    init_db()
