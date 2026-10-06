// ==========================================
// SYSTEM STATE & LOCAL DATABASE SIMULATION
// ==========================================

const DB_KEYS = {
    USERS: 'tf_users',
    ATTENDANCE: 'tf_attendance',
    WEIGHTS: 'tf_weights',
    SALARIES: 'tf_salaries',
    RATES: 'tf_rates'
};

// Initial Mock Data to ensure the system is wowed and fully functional on first load!
const DEFAULT_RATES = {
    above_80: 60,
    between_70_80: 50,
    below_70: 40,
    male_daily: 2000,
    female_daily: 1500
};

// We pre-generate realistic daily logs for the last 10 days (from May 17 to May 26, 2026)
const getInitialMockData = () => {
    const users = [
        { user_id: 101, name: "Aruna Perera", role: "owner", gender: "Male", phone: "0771112222", password: "owner123" },
        { user_id: 201, name: "Kamal Silva", role: "supervisor", gender: "Male", phone: "0773334444", password: "super123", area: "Tea Field A" },
        { user_id: 202, name: "Nimali Fernando", role: "supervisor", gender: "Female", phone: "0775556666", password: "super123", area: "Factory Processing" },
        
        // Servants - Tea Collectors
        { user_id: 301, name: "Kusal Mendis", role: "servant", gender: "Male", phone: "0777778888", password: "servant123", work_type: "Tea Collector" },
        { user_id: 302, name: "Anura Bandaranaike", role: "servant", gender: "Male", phone: "0779990000", password: "servant123", work_type: "Tea Collector" },
        
        // Servants - Retail Workers
        { user_id: 303, name: "Pathum Nissanka", role: "servant", gender: "Male", phone: "0772223333", password: "servant123", work_type: "Retail Worker" },
        { user_id: 304, name: "Chamari Athapaththu", role: "servant", gender: "Female", phone: "0774445555", password: "servant123", work_type: "Retail Worker" }
    ];

    const attendance = [];
    const weights = [];
    const salaries = [];
    
    // Generate records for the last 10 days: May 17 to May 26, 2026
    const startDate = new Date("2026-05-17");
    
    for (let d = 0; d < 10; d++) {
        const currentDate = new Date(startDate);
        currentDate.setDate(startDate.getDate() + d);
        const dateStr = currentDate.toISOString().split('T')[0];
        
        // Kusal Mendis (301): Tea Collector. Works 9 out of 10 days (90% attendance)
        const present301 = d !== 3; // absent on 4th day
        attendance.push({
            attendance_id: 1000 + d*4 + 1,
            servant_id: 301,
            date: dateStr,
            check_in: present301 ? "07:30" : null,
            check_out: present301 ? "16:45" : null,
            status: present301 ? "Present" : "Absent"
        });
        if (present301) {
            // Collects weight daily. Rain on Day 2 and Day 7
            const isRain = (d === 2 || d === 7);
            const originalWeight = Math.round((50 + Math.random() * 40) * 10) / 10; // 50kg - 90kg
            const deduction = isRain ? originalWeight / 20 : 0;
            const adjustedWeight = Math.round((originalWeight - deduction) * 10) / 10;
            
            weights.push({
                weight_id: 2000 + d*2 + 1,
                servant_id: 301,
                date: dateStr,
                original_weight: originalWeight,
                adjusted_weight: adjustedWeight,
                rainy_day: isRain,
                area: d % 2 === 0 ? "Tea Field A" : "Tea Field B"
            });
        }

        // Anura Bandaranaike (302): Tea Collector. Works 7 out of 10 days (70% attendance)
        const present302 = (d !== 1 && d !== 5 && d !== 8); 
        attendance.push({
            attendance_id: 1000 + d*4 + 2,
            servant_id: 302,
            date: dateStr,
            check_in: present302 ? "07:45" : null,
            check_out: present302 ? "17:00" : null,
            status: present302 ? "Present" : "Absent"
        });
        if (present302) {
            const isRain = (d === 2 || d === 7);
            const originalWeight = Math.round((40 + Math.random() * 35) * 10) / 10; // 40kg - 75kg
            const deduction = isRain ? originalWeight / 20 : 0;
            const adjustedWeight = Math.round((originalWeight - deduction) * 10) / 10;
            
            weights.push({
                weight_id: 2000 + d*2 + 2,
                servant_id: 302,
                date: dateStr,
                original_weight: originalWeight,
                adjusted_weight: adjustedWeight,
                rainy_day: isRain,
                area: d % 2 === 0 ? "Tea Field B" : "Factory Processing"
            });
        }

        // Pathum Nissanka (303): Retail Worker (Male). Works 8 out of 10 days
        const present303 = (d !== 4 && d !== 9);
        attendance.push({
            attendance_id: 1000 + d*4 + 3,
            servant_id: 303,
            date: dateStr,
            check_in: present303 ? "08:00" : null,
            check_out: present303 ? "17:00" : null,
            status: present303 ? "Present" : "Absent"
        });

        // Chamari Athapaththu (304): Retail Worker (Female). Works 10 out of 10 days (100%)
        attendance.push({
            attendance_id: 1000 + d*4 + 4,
            servant_id: 304,
            date: dateStr,
            check_in: "07:55",
            check_out: "17:15",
            status: "Present"
        });
    }

    return { users, attendance, weights, salaries };
};

// State Store Manager
const tfDb = {
    get: (key) => {
        const val = localStorage.getItem(key);
        return val ? JSON.parse(val) : null;
    },
    set: (key, val) => {
        localStorage.setItem(key, JSON.stringify(val));
    },
    init: () => {
        if (!localStorage.getItem(DB_KEYS.USERS)) {
            const initial = getInitialMockData();
            tfDb.set(DB_KEYS.USERS, initial.users);
            tfDb.set(DB_KEYS.ATTENDANCE, initial.attendance);
            tfDb.set(DB_KEYS.WEIGHTS, initial.weights);
            tfDb.set(DB_KEYS.SALARIES, initial.salaries);
            tfDb.set(DB_KEYS.RATES, DEFAULT_RATES);
            console.log("Database initialized with premium 10-day mock data.");
        }
    }
};

tfDb.init();

// Active Session Cache
let currentUser = JSON.parse(sessionStorage.getItem('tf_session')) || null;
let activeTab = 'dashboard';
let globalChartInstance = null;
let subChart1Instance = null;
let subChart2Instance = null;

// ==========================================
// TOAST NOTIFICATIONS WIDGET
// ==========================================
const showToast = (message, type = 'success') => {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    let icon = 'info';
    if (type === 'success') icon = 'check-circle';
    if (type === 'error') icon = 'alert-triangle';
    
    toast.innerHTML = `<i data-feather="${icon}" style="width: 18px; height: 18px;"></i> <span>${message}</span>`;
    container.appendChild(toast);
    feather.replace();
    
    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s ease reverse';
        setTimeout(() => toast.remove(), 300);
    }, 3500);
};

// ==========================================
// SYSTEM AUTHENTICATION LOGIC
// ==========================================
const handleLogin = () => {
    const phoneInput = document.getElementById('login-phone').value.trim();
    const passwordInput = document.getElementById('login-password').value;
    
    const users = tfDb.get(DB_KEYS.USERS);
    const matchedUser = users.find(u => u.phone === phoneInput && u.password === passwordInput);
    
    if (matchedUser) {
        currentUser = matchedUser;
        sessionStorage.setItem('tf_session', JSON.stringify(currentUser));
        
        showToast(`Welcome back, ${currentUser.name}!`, 'success');
        document.getElementById('auth-view').style.display = 'none';
        document.getElementById('app-shell').style.display = 'grid';
        
        initializeViewsByRole();
        switchTab('dashboard');
        
        // Reset login form fields
        document.getElementById('login-phone').value = '';
        document.getElementById('login-password').value = '';
    } else {
        showToast('Invalid credentials! Please try again.', 'error');
    }
};

const handleLogout = () => {
    currentUser = null;
    sessionStorage.removeItem('tf_session');
    
    document.getElementById('app-shell').style.display = 'none';
    document.getElementById('auth-view').style.display = 'flex';
    showToast('Signed out successfully.', 'info');
};

// ==========================================
// ROLE BASED NAVIGATION VIEW ENGINE
// ==========================================
const initializeViewsByRole = () => {
    if (!currentUser) return;
    
    // Set Sidebar Badges
    const initials = currentUser.name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
    document.getElementById('user-avatar').innerText = initials;
    document.getElementById('user-display-name').innerText = currentUser.name;
    document.getElementById('user-display-role').innerText = currentUser.role;
    
    // Update live footer banner date
    const dateOpts = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    document.getElementById('live-time').innerText = new Date("2026-05-26").toLocaleDateString('en-US', dateOpts);
    
    // Filter Navigation Tabs
    const role = currentUser.role;
    
    // Hide all role-specific list items
    document.querySelectorAll('.sidebar-menu li').forEach(el => {
        el.style.display = 'none';
    });
    
    // Always show generic dashboard
    document.getElementById('menu-dashboard').style.display = 'flex';
    
    if (role === 'owner') {
        document.getElementById('menu-supervisors').style.display = 'flex';
        document.getElementById('menu-servants').style.display = 'flex';
        document.getElementById('menu-salary').style.display = 'flex';
        document.getElementById('menu-reports').style.display = 'flex';
    } else if (role === 'supervisor') {
        document.getElementById('menu-servants').style.display = 'flex';
        document.getElementById('menu-attendance').style.display = 'flex';
        document.getElementById('menu-weights').style.display = 'flex';
    } else if (role === 'servant') {
        document.getElementById('menu-servant-records').style.display = 'flex';
    }
    
    feather.replace();
};

const switchTab = (tabId) => {
    activeTab = tabId;
    
    // Deactivate all menus & views
    document.querySelectorAll('.sidebar-menu li').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.dashboard-view').forEach(el => el.classList.remove('active'));
    
    // Activate clicked menu & view
    const menuEl = document.getElementById(`menu-${tabId}`);
    if (menuEl) menuEl.classList.add('active');
    
    const viewEl = document.getElementById(`view-${tabId}`);
    if (viewEl) viewEl.classList.add('active');
    
    // Set Navigation Page Header Title
    let pageTitle = "Dashboard Overview";
    if (tabId === 'supervisors') pageTitle = "Manage Factory Supervisors";
    if (tabId === 'servants') pageTitle = "Manage Servant Workers";
    if (tabId === 'attendance') pageTitle = "Mark Servant Attendance Logs";
    if (tabId === 'weights') pageTitle = "Tea Weight Daily Collector";
    if (tabId === 'salary') pageTitle = "Servant Payroll Processing Hub";
    if (tabId === 'reports') pageTitle = "Operational Productivity Reports";
    if (tabId === 'servant-records') pageTitle = "My Personal Performance Board";
    
    document.getElementById('current-tab-title').innerText = pageTitle;
    
    // Close sidebar on mobile
    document.getElementById('sidebar-nav').classList.remove('mobile-open');
    
    // Run view specific trigger loaders
    loadViewData(tabId);
};

const toggleMobileSidebar = () => {
    document.getElementById('sidebar-nav').classList.toggle('mobile-open');
};

// ==========================================
// CENTRAL VIEW DATA DISPATCH ROUTER
// ==========================================
const loadViewData = (tabId) => {
    if (tabId === 'dashboard') loadDashboardView();
    if (tabId === 'supervisors') loadSupervisorsTable();
    if (tabId === 'servants') loadServantsTable();
    if (tabId === 'attendance') {
        // Default date picker to today in simulated timeline: May 26, 2026
        document.getElementById('attendance-date').value = "2026-05-26";
        loadAttendanceSheet();
    }
    if (tabId === 'weights') {
        loadTeaWeightPanel();
    }
    if (tabId === 'salary') {
        document.getElementById('salary-start-date').value = "2026-05-17";
        document.getElementById('salary-end-date').value = "2026-05-26";
        loadSalaryConfigView();
    }
    if (tabId === 'reports') loadReportsCharts();
    if (tabId === 'servant-records') loadServantActivityBoard();
};

// ==========================================
// 1. DASHBOARD COMPILATION LAYER
// ==========================================
const loadDashboardView = () => {
    if (!currentUser) return;
    
    // Personalize Hero text
    document.getElementById('hero-welcome').innerText = `Welcome Back, ${currentUser.name}!`;
    
    let welcomeDesc = "Automate worker check-ins, record tea weight with dynamic rainy day deductions, and run smart 10-day salary cycles in one unified dashboard.";
    if (currentUser.role === 'supervisor') {
        welcomeDesc = `Supervising operational field today. Record servant attendances, assign tea plots, and weigh leaf bags with rainy day rules.`;
    } else if (currentUser.role === 'servant') {
        const type = currentUser.work_type === 'Tea Collector' ? 'Tea Harvesting' : 'Retail Processing';
        welcomeDesc = `My Personal Worker Dashboard. Assigned Area: ${currentUser.work_type}. Keep track of your daily bag weights, attendance rates, and estimated payouts.`;
    }
    document.getElementById('hero-desc').innerText = welcomeDesc;
    
    // Compile Metrics and widgets depending on roles
    const statsGrid = document.getElementById('dashboard-stats');
    const sideTitle = document.getElementById('panel-side-title');
    const sideBody = document.getElementById('panel-side-body');
    const mainTitle = document.getElementById('panel-main-title');
    
    statsGrid.innerHTML = '';
    
    const users = tfDb.get(DB_KEYS.USERS);
    const attendance = tfDb.get(DB_KEYS.ATTENDANCE);
    const weights = tfDb.get(DB_KEYS.WEIGHTS);
    const salaries = tfDb.get(DB_KEYS.SALARIES);
    const rates = tfDb.get(DB_KEYS.RATES);
    
    if (currentUser.role === 'owner' || currentUser.role === 'supervisor') {
        // Owner & Supervisor stats
        const supervisorCount = users.filter(u => u.role === 'supervisor').length;
        const servantCount = users.filter(u => u.role === 'servant').length;
        const totalWeight = weights.reduce((acc, curr) => acc + curr.adjusted_weight, 0);
        
        // Sum total simulated payout
        let estimatedPayout = 0;
        const compiledSalaries = compileSalaryRecords("2026-05-17", "2026-05-26");
        compiledSalaries.forEach(item => {
            estimatedPayout += item.salary;
        });

        // 1. Supervisors Stat
        statsGrid.innerHTML += `
            <div class="glass-card stat-card">
                <div class="stat-details">
                    <h4>Supervisors</h4>
                    <div class="value">${supervisorCount}</div>
                    <div class="trend positive"><i data-feather="users" style="width: 14px; height: 14px;"></i> Active Supervisors</div>
                </div>
                <div class="stat-icon" style="background: rgba(6, 182, 212, 0.1); color: var(--secondary);">
                    <i data-feather="users"></i>
                </div>
            </div>
            
            <div class="glass-card stat-card">
                <div class="stat-details">
                    <h4>Servant Workers</h4>
                    <div class="value">${servantCount}</div>
                    <div class="trend positive"><i data-feather="user-check" style="width: 14px; height: 14px;"></i> Active Servants</div>
                </div>
                <div class="stat-icon" style="background: rgba(16, 185, 129, 0.1); color: var(--primary);">
                    <i data-feather="user-check"></i>
                </div>
            </div>

            <div class="glass-card stat-card">
                <div class="stat-details">
                    <h4>10-Day Tea Harvest</h4>
                    <div class="value">${Math.round(totalWeight)} kg</div>
                    <div class="trend positive"><i data-feather="trending-up" style="width: 14px; height: 14px;"></i> Total Net Weight</div>
                </div>
                <div class="stat-icon" style="background: rgba(245, 158, 11, 0.1); color: var(--warning);">
                    <i data-feather="scale"></i>
                </div>
            </div>

            <div class="glass-card stat-card">
                <div class="stat-details">
                    <h4>Estimated Payout</h4>
                    <div class="value">Rs. ${estimatedPayout.toLocaleString()}</div>
                    <div class="trend positive"><i data-feather="credit-card" style="width: 14px; height: 14px;"></i> Simulated 10-day Run</div>
                </div>
                <div class="stat-icon" style="background: rgba(59, 130, 246, 0.1); color: var(--info);">
                    <i data-feather="dollar-sign"></i>
                </div>
            </div>
        `;
        
        mainTitle.innerText = "Daily Tea Harvest Yield Trend";
        
        // Side widget: Quick Area Breakdown
        sideTitle.innerText = "Work Area allocations";
        const areaDistribution = {
            'Tea Field A': 0,
            'Tea Field B': 0,
            'Factory Processing': 0,
            'Packaging Section': 0
        };
        weights.forEach(w => {
            if (areaDistribution[w.area] !== undefined) {
                areaDistribution[w.area] += w.adjusted_weight;
            }
        });
        
        sideBody.innerHTML = `
            <div style="display: flex; flex-direction: column; gap: 14px;">
                ${Object.entries(areaDistribution).map(([area, val]) => `
                    <div>
                        <div style="display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 6px;">
                            <span>${area}</span>
                            <span style="font-weight: 700; color: var(--primary-light);">${Math.round(val)} kg</span>
                        </div>
                        <div style="height: 6px; background: rgba(255,255,255,0.05); border-radius: 4px; overflow: hidden;">
                            <div style="width: ${Math.min(100, (val/totalWeight)*100)}%; height: 100%; background: var(--primary); border-radius: 4px;"></div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
        
        // Compile Dashboard Chart
        setTimeout(() => {
            renderDashboardMainChart(weights);
        }, 100);
        
    } else if (currentUser.role === 'servant') {
        // Servant Metrics
        const myWeights = weights.filter(w => w.servant_id === currentUser.user_id);
        const myAttendance = attendance.filter(a => a.servant_id === currentUser.user_id);
        
        const totalKg = myWeights.reduce((acc, curr) => acc + curr.adjusted_weight, 0);
        const presentDays = myAttendance.filter(a => a.status === 'Present').length;
        const totalDays = 10; // 10-day period
        const attPct = Math.round((presentDays / totalDays) * 100);
        
        // Determine applied rate based on attendance percent
        let ratePerKg = rates.below_70;
        if (attPct > 80) ratePerKg = rates.above_80;
        else if (attPct >= 70) ratePerKg = rates.between_70_80;
        
        let calculatedSalary = 0;
        let statUnit = '';
        let statRateLabel = '';
        
        if (currentUser.work_type === 'Tea Collector') {
            calculatedSalary = totalKg * ratePerKg;
            statUnit = `${Math.round(totalKg)} kg`;
            statRateLabel = `Rs. ${ratePerKg} / kg`;
        } else {
            // Retail Worker
            const dayRate = currentUser.gender === 'Male' ? rates.male_daily : rates.female_daily;
            calculatedSalary = presentDays * dayRate;
            statUnit = `${presentDays} Days`;
            statRateLabel = `Rs. ${dayRate} / Day`;
        }

        statsGrid.innerHTML += `
            <div class="glass-card stat-card">
                <div class="stat-details">
                    <h4>My Attendance Rate</h4>
                    <div class="value">${attPct}%</div>
                    <div class="trend positive"><i data-feather="calendar" style="width: 14px; height: 14px;"></i> ${presentDays} of 10 Days</div>
                </div>
                <div class="stat-icon" style="background: rgba(16, 185, 129, 0.1); color: var(--primary);">
                    <i data-feather="calendar"></i>
                </div>
            </div>
            
            <div class="glass-card stat-card">
                <div class="stat-details">
                    <h4>Total Output</h4>
                    <div class="value">${statUnit}</div>
                    <div class="trend positive"><i data-feather="trending-up" style="width: 14px; height: 14px;"></i> Adjusted Performance</div>
                </div>
                <div class="stat-icon" style="background: rgba(245, 158, 11, 0.1); color: var(--warning);">
                    <i data-feather="bar-chart-2"></i>
                </div>
            </div>

            <div class="glass-card stat-card">
                <div class="stat-details">
                    <h4>Current Base Rate</h4>
                    <div class="value">${statRateLabel}</div>
                    <div class="trend positive"><i data-feather="check-circle" style="width: 14px; height: 14px;"></i> Bracket Applied</div>
                </div>
                <div class="stat-icon" style="background: rgba(6, 182, 212, 0.1); color: var(--secondary);">
                    <i data-feather="activity"></i>
                </div>
            </div>

            <div class="glass-card stat-card">
                <div class="stat-details">
                    <h4>Est. 10-day Payout</h4>
                    <div class="value">Rs. ${Math.round(calculatedSalary).toLocaleString()}</div>
                    <div class="trend positive"><i data-feather="dollar-sign" style="width: 14px; height: 14px;"></i> Subject to adjustments</div>
                </div>
                <div class="stat-icon" style="background: rgba(59, 130, 246, 0.1); color: var(--info);">
                    <i data-feather="credit-card"></i>
                </div>
            </div>
        `;
        
        mainTitle.innerText = "My Daily Collection Track (Last 10 days)";
        
        // Side widget: Dynamic Attendance Ring & Rate Gauge
        sideTitle.innerText = "Attendance Bracket Tracker";
        
        if (currentUser.work_type === 'Tea Collector') {
            const circumference = 2 * Math.PI * 70; // r=70
            const offset = circumference - (attPct / 100) * circumference;
            
            sideBody.innerHTML = `
                <div class="attendance-ring-container">
                    <svg class="attendance-ring">
                        <circle class="ring-circle-bg" cx="75" cy="75" r="70"></circle>
                        <circle class="ring-circle-val" cx="75" cy="75" r="70" style="stroke-dasharray: ${circumference}; stroke-dashoffset: ${offset};"></circle>
                    </svg>
                    <div class="attendance-text">
                        <div class="attendance-pct">${attPct}%</div>
                        <div class="attendance-label">Rate Bracket</div>
                    </div>
                </div>
                <div class="salary-brackets">
                    <div class="bracket-item ${attPct > 80 ? 'highlight' : ''}">
                        <span class="bracket-range">&gt; 80% Attendance</span>
                        <span class="bracket-rate">Rs. ${rates.above_80} / kg</span>
                    </div>
                    <div class="bracket-item ${attPct >= 70 && attPct <= 80 ? 'highlight' : ''}">
                        <span class="bracket-range">70% - 80% Attendance</span>
                        <span class="bracket-rate">Rs. ${rates.between_70_80} / kg</span>
                    </div>
                    <div class="bracket-item ${attPct < 70 ? 'highlight' : ''}">
                        <span class="bracket-range">&lt; 70% Attendance</span>
                        <span class="bracket-rate">Rs. ${rates.below_70} / kg</span>
                    </div>
                </div>
            `;
        } else {
            // Retail worker sidebar
            const genderRateLabel = currentUser.gender === 'Male' ? 'Male Rate' : 'Female Rate';
            const genderDayRate = currentUser.gender === 'Male' ? rates.male_daily : rates.female_daily;
            sideBody.innerHTML = `
                <div style="text-align: center; padding: 20px;">
                    <i data-feather="gift" style="width: 50px; height: 50px; color: var(--primary); margin-bottom: 12px;"></i>
                    <h4 style="margin-bottom: 8px;">Retail Daily Wage Policy</h4>
                    <p style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.4; margin-bottom: 16px;">
                        Retail workers are paid a fixed daily wage based on gender rules. 
                    </p>
                    <div class="bracket-item highlight">
                        <span class="bracket-range">${genderRateLabel} Profile</span>
                        <span class="bracket-rate">Rs. ${genderDayRate} / Day</span>
                    </div>
                </div>
            `;
            feather.replace();
        }
        
        // Compile Servant Dashboard Chart
        setTimeout(() => {
            renderServantMainChart(myWeights, myAttendance);
        }, 100);
    }
    
    feather.replace();
};

const renderDashboardMainChart = (weights) => {
    const ctx = document.getElementById('dashboardMainChart').getContext('2d');
    if (globalChartInstance) globalChartInstance.destroy();
    
    // Group weights by date
    const dateMap = {};
    weights.forEach(w => {
        dateMap[w.date] = (dateMap[w.date] || 0) + w.adjusted_weight;
    });
    
    const dates = Object.keys(dateMap).sort();
    const dataVals = dates.map(d => Math.round(dateMap[d] * 10) / 10);
    
    globalChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: dates.map(d => d.substring(5)), // MM-DD
            datasets: [{
                label: 'Total Tea Harvest (kg)',
                data: dataVals,
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                borderWidth: 3,
                fill: true,
                tension: 0.4,
                pointBackgroundColor: '#10b981',
                pointHoverRadius: 7
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#64748b' }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#64748b' }
                }
            }
        }
    });
};

const renderServantMainChart = (myWeights, myAttendance) => {
    const ctx = document.getElementById('dashboardMainChart').getContext('2d');
    if (globalChartInstance) globalChartInstance.destroy();
    
    // Render dual collection & attendance status log
    const dateMap = {};
    myWeights.forEach(w => {
        dateMap[w.date] = w.adjusted_weight;
    });
    
    const sortedDates = Object.keys(dateMap).sort();
    const weightsData = sortedDates.map(d => dateMap[d]);
    
    globalChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: sortedDates.map(d => d.substring(5)),
            datasets: [{
                label: 'My Collection (kg)',
                data: weightsData,
                backgroundColor: 'rgba(16, 185, 129, 0.65)',
                hoverBackgroundColor: '#10b981',
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#64748b' }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#64748b' }
                }
            }
        }
    });
};

// ==========================================
// 2. SUPERVISORS CONTROLLER (OWNER ONLY)
// ==========================================
const loadSupervisorsTable = () => {
    const users = tfDb.get(DB_KEYS.USERS);
    const supervisors = users.filter(u => u.role === 'supervisor');
    const tbody = document.getElementById('supervisors-table-body');
    tbody.innerHTML = '';
    
    supervisors.forEach(s => {
        tbody.innerHTML += `
            <tr>
                <td><strong>SUP-${s.user_id}</strong></td>
                <td>${s.name}</td>
                <td>${s.gender}</td>
                <td>${s.phone}</td>
                <td><span class="badge badge-info">${s.area || 'All Sections'}</span></td>
                <td>
                    <button class="btn btn-secondary btn-sm" onclick="openEditUserModal(${s.user_id}, 'supervisor')" style="margin-right: 6px;">
                        <i data-feather="edit-2" style="width: 13px; height: 13px;"></i> Edit
                    </button>
                    <button class="btn btn-danger btn-sm" onclick="deleteUser(${s.user_id})">
                        <i data-feather="trash-2" style="width: 13px; height: 13px;"></i> Delete
                    </button>
                </td>
            </tr>
        `;
    });
    feather.replace();
};

// ==========================================
// 3. SERVANTS CONTROLLER
// ==========================================
const loadServantsTable = () => {
    const users = tfDb.get(DB_KEYS.USERS);
    const servants = users.filter(u => u.role === 'servant');
    const tbody = document.getElementById('servants-table-body');
    tbody.innerHTML = '';
    
    servants.forEach(s => {
        const typeBadge = s.work_type === 'Tea Collector' ? 'badge-success' : 'badge-warning';
        tbody.innerHTML += `
            <tr>
                <td><strong>SRV-${s.user_id}</strong></td>
                <td>${s.name}</td>
                <td>${s.gender}</td>
                <td><span class="badge ${typeBadge}">${s.work_type || 'Tea Collector'}</span></td>
                <td>${s.phone}</td>
                <td><span class="badge badge-success">Active</span></td>
                <td>
                    <button class="btn btn-secondary btn-sm" onclick="openEditUserModal(${s.user_id}, 'servant')" style="margin-right: 6px;">
                        <i data-feather="edit-2" style="width: 13px; height: 13px;"></i> Edit
                    </button>
                    ${currentUser.role === 'owner' ? `
                    <button class="btn btn-danger btn-sm" onclick="deleteUser(${s.user_id})">
                        <i data-feather="trash-2" style="width: 13px; height: 13px;"></i> Delete
                    </button>` : ''}
                </td>
            </tr>
        `;
    });
    feather.replace();
};

// ==========================================
// USER CREATION & MANAGEMENT MODAL
// ==========================================
const openAddUserModal = (role) => {
    document.getElementById('user-modal-title').innerText = `Add New ${role === 'supervisor' ? 'Supervisor' : 'Servant Worker'}`;
    document.getElementById('user-modal-id').value = '';
    document.getElementById('user-modal-role').value = role;
    
    document.getElementById('user-name').value = '';
    document.getElementById('user-phone').value = '';
    document.getElementById('user-password').value = '';
    document.getElementById('user-gender').value = 'Male';
    
    const areaContainer = document.getElementById('user-area-container');
    const typeContainer = document.getElementById('user-work-type-container');
    
    if (role === 'supervisor') {
        areaContainer.style.display = 'block';
        typeContainer.style.display = 'none';
    } else {
        areaContainer.style.display = 'none';
        typeContainer.style.display = 'block';
        document.getElementById('user-work-type').value = 'Tea Collector';
    }
    
    document.getElementById('user-modal').classList.add('active');
    feather.replace();
};

const openEditUserModal = (userId, role) => {
    const users = tfDb.get(DB_KEYS.USERS);
    const user = users.find(u => u.user_id === userId);
    if (!user) return;
    
    document.getElementById('user-modal-title').innerText = `Edit User Details`;
    document.getElementById('user-modal-id').value = user.user_id;
    document.getElementById('user-modal-role').value = user.role;
    
    document.getElementById('user-name').value = user.name;
    document.getElementById('user-phone').value = user.phone;
    document.getElementById('user-password').value = user.password;
    document.getElementById('user-gender').value = user.gender;
    
    const areaContainer = document.getElementById('user-area-container');
    const typeContainer = document.getElementById('user-work-type-container');
    
    if (user.role === 'supervisor') {
        areaContainer.style.display = 'block';
        typeContainer.style.display = 'none';
        document.getElementById('user-area').value = user.area || 'Tea Field A';
    } else {
        areaContainer.style.display = 'none';
        typeContainer.style.display = 'block';
        document.getElementById('user-work-type').value = user.work_type || 'Tea Collector';
    }
    
    document.getElementById('user-modal').classList.add('active');
    feather.replace();
};

const closeUserModal = () => {
    document.getElementById('user-modal').classList.remove('active');
};

const saveUser = () => {
    const userIdInput = document.getElementById('user-modal-id').value;
    const roleInput = document.getElementById('user-modal-role').value;
    const name = document.getElementById('user-name').value.trim();
    const phone = document.getElementById('user-phone').value.trim();
    const password = document.getElementById('user-password').value;
    const gender = document.getElementById('user-gender').value;
    
    let users = tfDb.get(DB_KEYS.USERS);
    
    if (userIdInput) {
        // Edit Mode
        const id = parseInt(userIdInput);
        const idx = users.findIndex(u => u.user_id === id);
        if (idx !== -1) {
            users[idx].name = name;
            users[idx].phone = phone;
            users[idx].password = password;
            users[idx].gender = gender;
            
            if (roleInput === 'supervisor') {
                users[idx].area = document.getElementById('user-area').value;
            } else {
                users[idx].work_type = document.getElementById('user-work-type').value;
            }
            showToast('User details updated successfully!', 'success');
        }
    } else {
        // Add Mode
        const newId = users.reduce((max, u) => u.user_id > max ? u.user_id : max, 300) + 1;
        const newUser = {
            user_id: newId,
            name,
            role: roleInput,
            gender,
            phone,
            password
        };
        
        if (roleInput === 'supervisor') {
            newUser.area = document.getElementById('user-area').value;
        } else {
            newUser.work_type = document.getElementById('user-work-type').value;
        }
        
        users.push(newUser);
        showToast('New user registered successfully!', 'success');
    }
    
    tfDb.set(DB_KEYS.USERS, users);
    closeUserModal();
    
    if (roleInput === 'supervisor') loadSupervisorsTable();
    else loadServantsTable();
};

const deleteUser = (userId) => {
    if (confirm("Are you sure you want to delete this user profile?")) {
        let users = tfDb.get(DB_KEYS.USERS);
        const matched = users.find(u => u.user_id === userId);
        
        users = users.filter(u => u.user_id !== userId);
        tfDb.set(DB_KEYS.USERS, users);
        showToast('User removed from system.', 'error');
        
        if (matched && matched.role === 'supervisor') loadSupervisorsTable();
        else loadServantsTable();
    }
};

// ==========================================
// 4. ATTENDANCE LOGGER (SUPERVISOR ONLY)
// ==========================================
const loadAttendanceSheet = () => {
    const selectedDate = document.getElementById('attendance-date').value;
    if (!selectedDate) return;
    
    const users = tfDb.get(DB_KEYS.USERS);
    const servants = users.filter(u => u.role === 'servant');
    const attendance = tfDb.get(DB_KEYS.ATTENDANCE);
    
    const tbody = document.getElementById('attendance-table-body');
    tbody.innerHTML = '';
    
    servants.forEach(s => {
        // Find existing record or build blank template
        let record = attendance.find(a => a.servant_id === s.user_id && a.date === selectedDate);
        if (!record) {
            record = {
                attendance_id: null,
                servant_id: s.user_id,
                date: selectedDate,
                check_in: null,
                check_out: null,
                status: 'Absent'
            };
        }
        
        const isPresent = record.status === 'Present';
        const inVal = record.check_in || '';
        const outVal = record.check_out || '';
        
        const badgeClass = isPresent ? 'badge-success' : 'badge-danger';
        const typeBadge = s.work_type === 'Tea Collector' ? 'badge-success' : 'badge-warning';
        
        tbody.innerHTML += `
            <tr id="att-row-${s.user_id}">
                <td>
                    <div style="font-weight: 600;">${s.name}</div>
                    <span style="font-size: 0.75rem; color: var(--text-secondary);">SRV-${s.user_id}</span>
                </td>
                <td><span class="badge ${typeBadge}">${s.work_type}</span></td>
                <td>${s.gender}</td>
                <td>
                    <span id="att-status-${s.user_id}" class="badge ${badgeClass}">${record.status}</span>
                </td>
                <td>
                    <input type="time" id="time-in-${s.user_id}" class="glass-input" style="padding: 6px 12px; width: 120px;" value="${inVal}" onchange="updateAttendanceRecord(${s.user_id})">
                </td>
                <td>
                    <input type="time" id="time-out-${s.user_id}" class="glass-input" style="padding: 6px 12px; width: 120px;" value="${outVal}" onchange="updateAttendanceRecord(${s.user_id})">
                </td>
                <td>
                    <button class="btn btn-secondary btn-sm" onclick="quickMarkPresent(${s.user_id})">
                        <i data-feather="check" style="width: 13px; height: 13px;"></i> Quick Present
                    </button>
                    <button class="btn btn-danger btn-sm" onclick="quickMarkAbsent(${s.user_id})" style="margin-left: 6px;">
                        <i data-feather="x" style="width: 13px; height: 13px;"></i> Absent
                    </button>
                </td>
            </tr>
        `;
    });
    feather.replace();
};

const updateAttendanceRecord = (servantId) => {
    const selectedDate = document.getElementById('attendance-date').value;
    const checkInTime = document.getElementById(`time-in-${servantId}`).value;
    const checkOutTime = document.getElementById(`time-out-${servantId}`).value;
    
    let attendance = tfDb.get(DB_KEYS.ATTENDANCE);
    let recordIdx = attendance.findIndex(a => a.servant_id === servantId && a.date === selectedDate);
    
    // Automatically present if check-in is logged
    const status = checkInTime ? 'Present' : 'Absent';
    
    if (recordIdx !== -1) {
        attendance[recordIdx].check_in = checkInTime || null;
        attendance[recordIdx].check_out = checkOutTime || null;
        attendance[recordIdx].status = status;
    } else {
        const newId = attendance.reduce((max, a) => a.attendance_id > max ? a.attendance_id : max, 1000) + 1;
        attendance.push({
            attendance_id: newId,
            servant_id: servantId,
            date: selectedDate,
            check_in: checkInTime || null,
            check_out: checkOutTime || null,
            status: status
        });
    }
    
    tfDb.set(DB_KEYS.ATTENDANCE, attendance);
    
    // Update visual badge without full reload for smoother UX
    const statusBadge = document.getElementById(`att-status-${servantId}`);
    if (statusBadge) {
        statusBadge.className = `badge ${status === 'Present' ? 'badge-success' : 'badge-danger'}`;
        statusBadge.innerText = status;
    }
};

const quickMarkPresent = (servantId) => {
    document.getElementById(`time-in-${servantId}`).value = "07:30";
    document.getElementById(`time-out-${servantId}`).value = "17:00";
    updateAttendanceRecord(servantId);
    showToast("Attendance logged: Present", "success");
};

const quickMarkAbsent = (servantId) => {
    document.getElementById(`time-in-${servantId}`).value = "";
    document.getElementById(`time-out-${servantId}`).value = "";
    updateAttendanceRecord(servantId);
    showToast("Attendance logged: Absent", "error");
};

// ==========================================
// 5. TEA WEIGHT CONTROLLER
// ==========================================
const loadTeaWeightPanel = () => {
    const users = tfDb.get(DB_KEYS.USERS);
    // Only load servants categorized as Tea Collectors
    const collectors = users.filter(u => u.role === 'servant' && u.work_type === 'Tea Collector');
    
    const select = document.getElementById('weight-servant-select');
    select.innerHTML = collectors.map(c => `<option value="${c.user_id}">${c.name}</option>`).join('');
    
    document.getElementById('weight-original').value = '';
    document.getElementById('weight-rainy-toggle').checked = false;
    document.getElementById('rainy-preview').style.display = 'none';
    
    loadDailyWeightsLog();
};

const updateRainyPreview = () => {
    const originalInput = parseFloat(document.getElementById('weight-original').value);
    const rainyChecked = document.getElementById('weight-rainy-toggle').checked;
    
    if (isNaN(originalInput) || originalInput <= 0) {
        document.getElementById('rainy-preview').style.display = 'none';
        return;
    }
    
    document.getElementById('rainy-preview').style.display = 'flex';
    document.getElementById('preview-original').innerText = `${originalInput.toFixed(1)} kg`;
    
    if (rainyChecked) {
        // Rainy day reduction: 1kg per every 20kg
        const deduction = originalInput / 20;
        const adjusted = originalInput - deduction;
        
        document.getElementById('preview-deduction').innerText = `${deduction.toFixed(2)} kg`;
        document.getElementById('preview-final').innerText = `${adjusted.toFixed(2)} kg`;
        document.getElementById('preview-deduction').parentElement.style.opacity = '1';
    } else {
        document.getElementById('preview-deduction').innerText = `0.0 kg`;
        document.getElementById('preview-final').innerText = `${originalInput.toFixed(1)} kg`;
        document.getElementById('preview-deduction').parentElement.style.opacity = '0.5';
    }
};

const submitTeaWeight = () => {
    const servantId = parseInt(document.getElementById('weight-servant-select').value);
    const area = document.getElementById('weight-area-select').value;
    const originalWeight = parseFloat(document.getElementById('weight-original').value);
    const rainyChecked = document.getElementById('weight-rainy-toggle').checked;
    
    if (isNaN(originalWeight) || originalWeight <= 0) {
        showToast('Please enter a valid Measured Weight!', 'error');
        return;
    }
    
    // Simulated timeline date is always May 26, 2026 for Supervisor additions
    const targetDate = "2026-05-26";
    
    const deduction = rainyChecked ? originalWeight / 20 : 0;
    const adjustedWeight = Math.round((originalWeight - deduction) * 100) / 100;
    
    let weights = tfDb.get(DB_KEYS.WEIGHTS);
    const newId = weights.reduce((max, w) => w.weight_id > max ? w.weight_id : max, 2000) + 1;
    
    weights.push({
        weight_id: newId,
        servant_id: servantId,
        date: targetDate,
        original_weight: originalWeight,
        adjusted_weight: adjustedWeight,
        rainy_day: rainyChecked,
        area: area
    });
    
    tfDb.set(DB_KEYS.WEIGHTS, weights);
    showToast('Tea weight record logged successfully!', 'success');
    
    // Clear forms & refresh
    document.getElementById('weight-original').value = '';
    document.getElementById('rainy-preview').style.display = 'none';
    
    loadDailyWeightsLog();
};

const loadDailyWeightsLog = () => {
    const weights = tfDb.get(DB_KEYS.WEIGHTS);
    const users = tfDb.get(DB_KEYS.USERS);
    
    // Load for Supervisor timeline date: May 26, 2026
    const targetDate = "2026-05-26";
    const dailyWeights = weights.filter(w => w.date === targetDate);
    
    const totalToday = dailyWeights.reduce((acc, curr) => acc + curr.adjusted_weight, 0);
    document.getElementById('today-total-weight-badge').innerText = `Total Today: ${Math.round(totalToday * 10) / 10} kg`;
    
    const tbody = document.getElementById('daily-weights-table-body');
    tbody.innerHTML = '';
    
    if (dailyWeights.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-secondary); padding: 20px;">No tea weight records logged today.</td></tr>`;
        return;
    }
    
    dailyWeights.forEach(w => {
        const servantName = users.find(u => u.user_id === w.servant_id)?.name || 'Unknown';
        const condBadge = w.rainy_day ? '<span class="badge badge-danger">Rainy (Reduced)</span>' : '<span class="badge badge-success">Dry Day</span>';
        
        tbody.innerHTML += `
            <tr>
                <td>${w.date}</td>
                <td><strong>${servantName}</strong></td>
                <td><span class="badge badge-info">${w.area}</span></td>
                <td>${w.original_weight} kg</td>
                <td>${condBadge}</td>
                <td style="font-weight: 700; color: var(--primary-light);">${w.adjusted_weight} kg</td>
                <td>
                    <button class="btn btn-danger btn-sm" onclick="deleteWeightRecord(${w.weight_id})">
                        <i data-feather="trash" style="width: 12px; height: 12px;"></i>
                    </button>
                </td>
            </tr>
        `;
    });
    feather.replace();
};

const deleteWeightRecord = (weightId) => {
    if (confirm("Are you sure you want to delete this weight measurement entry?")) {
        let weights = tfDb.get(DB_KEYS.WEIGHTS);
        weights = weights.filter(w => w.weight_id !== weightId);
        tfDb.set(DB_KEYS.WEIGHTS, weights);
        showToast("Tea weight record removed.", "error");
        loadDailyWeightsLog();
    }
};

// ==========================================
// 6. PAYROLL SYSTEM & DYNAMIC CALCULATOR
// ==========================================
const loadSalaryConfigView = () => {
    const rates = tfDb.get(DB_KEYS.RATES);
    
    document.getElementById('rate-above-80').value = rates.above_80;
    document.getElementById('rate-70-80').value = rates.between_70_80;
    document.getElementById('rate-below-70').value = rates.below_70;
    
    document.getElementById('rate-male-daily').value = rates.male_daily;
    document.getElementById('rate-female-daily').value = rates.female_daily;
    
    // Auto trigger compiling for standard 10 days
    triggerSalaryCompilation();
};

const saveGlobalRates = () => {
    const rates = {
        above_80: parseInt(document.getElementById('rate-above-80').value),
        between_70_80: parseInt(document.getElementById('rate-70-80').value),
        below_70: parseInt(document.getElementById('rate-below-70').value),
        male_daily: parseInt(document.getElementById('rate-male-daily').value),
        female_daily: parseInt(document.getElementById('rate-female-daily').value)
    };
    tfDb.set(DB_KEYS.RATES, rates);
    showToast('Payment rates updated successfully!', 'success');
};

const compileSalaryRecords = (startDate, endDate) => {
    const users = tfDb.get(DB_KEYS.USERS);
    const attendance = tfDb.get(DB_KEYS.ATTENDANCE);
    const weights = tfDb.get(DB_KEYS.WEIGHTS);
    const rates = tfDb.get(DB_KEYS.RATES);
    const paidRecords = tfDb.get(DB_KEYS.SALARIES);
    
    const servants = users.filter(u => u.role === 'servant');
    const result = [];
    
    // Compute date differences to verify full days of the cycle
    const d1 = new Date(startDate);
    const d2 = new Date(endDate);
    const diffTime = Math.abs(d2 - d1);
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24)) + 1;
    
    servants.forEach(s => {
        // Attendance percent in this range
        const myAtt = attendance.filter(a => a.servant_id === s.user_id && a.date >= startDate && a.date <= endDate);
        const presentDays = myAtt.filter(a => a.status === 'Present').length;
        const totalDays = diffDays;
        
        const attendancePct = totalDays > 0 ? Math.round((presentDays / totalDays) * 100) : 0;
        
        let displayOutput = '';
        let appliedRateStr = '';
        let calculatedSalary = 0;
        
        if (s.work_type === 'Tea Collector') {
            // Paid by weight
            const myWeights = weights.filter(w => w.servant_id === s.user_id && w.date >= startDate && w.date <= endDate);
            const totalWeight = myWeights.reduce((acc, curr) => acc + curr.adjusted_weight, 0);
            
            let rate = rates.below_70;
            if (attendancePct > 80) rate = rates.above_80;
            else if (attendancePct >= 70) rate = rates.between_70_80;
            
            calculatedSalary = Math.round(totalWeight * rate);
            displayOutput = `${Math.round(totalWeight * 10) / 10} kg`;
            appliedRateStr = `Rs. ${rate} / kg`;
        } else {
            // Retail worker paid daily based on gender
            const dayRate = s.gender === 'Male' ? rates.male_daily : rates.female_daily;
            calculatedSalary = presentDays * dayRate;
            displayOutput = `${presentDays} Days`;
            appliedRateStr = `Rs. ${dayRate} / Day`;
        }
        
        // Find if already recorded in salaries table (Paid)
        const isPaid = paidRecords.some(p => p.servant_id === s.user_id && p.start_date === startDate && p.end_date === endDate && p.status === 'Paid');
        
        result.push({
            servant_id: s.user_id,
            name: s.name,
            work_type: s.work_type,
            attendance_pct: attendancePct,
            output: displayOutput,
            rate: appliedRateStr,
            salary: calculatedSalary,
            is_paid: isPaid
        });
    });
    
    return result;
};

const triggerSalaryCompilation = () => {
    const startDate = document.getElementById('salary-start-date').value;
    const endDate = document.getElementById('salary-end-date').value;
    
    if (!startDate || !endDate) return;
    
    const compiled = compileSalaryRecords(startDate, endDate);
    const tbody = document.getElementById('salary-table-body');
    tbody.innerHTML = '';
    
    compiled.forEach(item => {
        const typeBadge = item.work_type === 'Tea Collector' ? 'badge-success' : 'badge-warning';
        const pctBadge = item.attendance_pct >= 80 ? 'badge-success' : (item.attendance_pct >= 70 ? 'badge-warning' : 'badge-danger');
        
        const statusBadge = item.is_paid 
            ? '<span class="badge badge-success">Paid</span>' 
            : '<span class="badge badge-warning">Pending</span>';
            
        const payBtn = item.is_paid 
            ? `<button class="btn btn-secondary btn-sm" disabled style="opacity: 0.5;">Paid</button>`
            : `<button class="btn btn-primary btn-sm" onclick="processPayment(${item.servant_id}, ${item.attendance_pct}, '${item.output}', '${item.rate}', ${item.salary})"><i data-feather="check"></i> Pay</button>`;
            
        tbody.innerHTML += `
            <tr>
                <td><strong>SRV-${item.servant_id}</strong></td>
                <td>${item.name}</td>
                <td><span class="badge ${typeBadge}">${item.work_type}</span></td>
                <td><span class="badge ${pctBadge}">${item.attendance_pct}%</span></td>
                <td style="font-weight:600;">${item.output}</td>
                <td style="color: var(--secondary); font-weight:500;">${item.rate}</td>
                <td style="font-weight: 700; color: var(--primary-light); font-size: 1.05rem;">Rs. ${item.salary.toLocaleString()}</td>
                <td id="pay-status-${item.servant_id}">${statusBadge}</td>
                <td id="pay-action-${item.servant_id}">${payBtn}</td>
            </tr>
        `;
    });
    feather.replace();
};

const compileSalaryRun = () => {
    triggerSalaryCompilation();
    showToast("Salaries compiled for selected 10-day timeline!", "success");
};

const processPayment = (servantId, attendancePct, outputStr, rateStr, totalSalary) => {
    const startDate = document.getElementById('salary-start-date').value;
    const endDate = document.getElementById('salary-end-date').value;
    
    let salaries = tfDb.get(DB_KEYS.SALARIES);
    const newId = salaries.reduce((max, s) => s.salary_id > max ? s.salary_id : max, 4000) + 1;
    
    // Parse output digits (weights or days)
    const totalOutput = parseFloat(outputStr);
    const paymentRate = parseFloat(rateStr.replace('Rs. ', ''));
    
    salaries.push({
        salary_id: newId,
        servant_id: servantId,
        start_date: startDate,
        end_date: endDate,
        attendance_percentage: attendancePct,
        total_weight: totalOutput,
        payment_rate: paymentRate,
        total_salary: totalSalary,
        status: 'Paid',
        date_processed: "2026-05-26"
    });
    
    tfDb.set(DB_KEYS.SALARIES, salaries);
    showToast(`Payment processed successfully for Servant SRV-${servantId}!`, 'success');
    
    // Visual Updates
    const statusContainer = document.getElementById(`pay-status-${servantId}`);
    const actionContainer = document.getElementById(`pay-action-${servantId}`);
    
    if (statusContainer) statusContainer.innerHTML = '<span class="badge badge-success">Paid</span>';
    if (actionContainer) actionContainer.innerHTML = `<button class="btn btn-secondary btn-sm" disabled style="opacity: 0.5;">Paid</button>`;
};

// ==========================================
// 7. ANALYTICS & REPORTS PAGE (OWNER ONLY)
// ==========================================
const loadReportsCharts = () => {
    const weights = tfDb.get(DB_KEYS.WEIGHTS);
    const salaries = tfDb.get(DB_KEYS.SALARIES);
    const users = tfDb.get(DB_KEYS.USERS);
    
    // Render 10-Day Tea Weight vs Salary Trend
    const ctx1 = document.getElementById('reportChartSalaryWeight').getContext('2d');
    if (subChart1Instance) subChart1Instance.destroy();
    
    // Calculate weights & estimated salaries per day
    const dates = [];
    const weightsByDate = [];
    const payoutByDate = [];
    
    const startDate = new Date("2026-05-17");
    for (let d = 0; d < 10; d++) {
        const currentDate = new Date(startDate);
        currentDate.setDate(startDate.getDate() + d);
        const dateStr = currentDate.toISOString().split('T')[0];
        
        dates.push(dateStr.substring(5));
        
        // Sum weights
        const dayWeights = weights.filter(w => w.date === dateStr);
        const dayWtTotal = dayWeights.reduce((acc, curr) => acc + curr.adjusted_weight, 0);
        weightsByDate.push(Math.round(dayWtTotal));
        
        // Mock daily proportional simulated salary
        payoutByDate.push(Math.round(dayWtTotal * 55)); // Average rate Rs. 55
    }
    
    subChart1Instance = new Chart(ctx1, {
        type: 'bar',
        data: {
            labels: dates,
            datasets: [
                {
                    label: 'Harvest Yield (kg)',
                    data: weightsByDate,
                    backgroundColor: 'rgba(16, 185, 129, 0.75)',
                    yAxisID: 'y'
                },
                {
                    label: 'Simulated Cost (Rs)',
                    data: payoutByDate,
                    type: 'line',
                    borderColor: '#06b6d4',
                    borderWidth: 3,
                    fill: false,
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#64748b' }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    grid: { drawOnChartArea: false },
                    ticks: { color: '#64748b' }
                },
                x: { ticks: { color: '#64748b' } }
            }
        }
    });

    // Render Pie Chart for Rainy Day Deductions Breakdown
    const ctx2 = document.getElementById('reportChartRainyDeduction').getContext('2d');
    if (subChart2Instance) subChart2Instance.destroy();
    
    let dryWeight = 0;
    let rainyOriginal = 0;
    let rainyDeductions = 0;
    
    weights.forEach(w => {
        if (w.rainy_day) {
            rainyOriginal += w.original_weight;
            rainyDeductions += (w.original_weight - w.adjusted_weight);
        } else {
            dryWeight += w.original_weight;
        }
    });
    
    subChart2Instance = new Chart(ctx2, {
        type: 'doughnut',
        data: {
            labels: ['Dry Day Harvest (kg)', 'Rainy Net Weight (kg)', 'Rain Weight Deductions (kg)'],
            datasets: [{
                data: [Math.round(dryWeight), Math.round(rainyOriginal - rainyDeductions), Math.round(rainyDeductions)],
                backgroundColor: ['#10b981', '#3b82f6', '#ef4444'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#f8fafc' }
                }
            }
        }
    });
    
    // Compile Worker Leaderboard
    compileLeaderboardTable(users, weights, tfDb.get(DB_KEYS.ATTENDANCE));
};

const compileLeaderboardTable = (users, weights, attendance) => {
    const collectors = users.filter(u => u.role === 'servant' && u.work_type === 'Tea Collector');
    const leaderboardData = [];
    
    collectors.forEach(c => {
        const myWeights = weights.filter(w => w.servant_id === c.user_id);
        const myAtt = attendance.filter(a => a.servant_id === c.user_id);
        
        const totalOriginal = myWeights.reduce((acc, curr) => acc + curr.original_weight, 0);
        const totalAdjusted = myWeights.reduce((acc, curr) => acc + curr.adjusted_weight, 0);
        const totalDeducted = totalOriginal - totalAdjusted;
        
        const presentDays = myAtt.filter(a => a.status === 'Present').length;
        const attPct = Math.round((presentDays / 10) * 100);
        
        // Efficiency index = Adjusted harvest divided by active days
        const avgHarvestPerDay = presentDays > 0 ? (totalAdjusted / presentDays) : 0;
        
        leaderboardData.push({
            name: c.name,
            original: totalOriginal,
            adjusted: totalAdjusted,
            deducted: totalDeducted,
            attendance: attPct,
            daily_avg: avgHarvestPerDay
        });
    });
    
    // Sort by net adjusted weight
    leaderboardData.sort((a, b) => b.adjusted - a.adjusted);
    
    const tbody = document.getElementById('leaderboard-table-body');
    tbody.innerHTML = '';
    
    leaderboardData.forEach((w, idx) => {
        let rankBadge = `<span style="font-weight: 700;">#${idx+1}</span>`;
        if (idx === 0) rankBadge = '<span class="badge badge-success">🥇 1st Rank</span>';
        if (idx === 1) rankBadge = '<span class="badge badge-info">🥈 2nd Rank</span>';
        
        let efficiencyBadge = '<span class="badge badge-danger">Needs Boost</span>';
        if (w.daily_avg > 60) efficiencyBadge = '<span class="badge badge-success">Harvest Master</span>';
        else if (w.daily_avg >= 40) efficiencyBadge = '<span class="badge badge-info">Consistent</span>';
        
        tbody.innerHTML += `
            <tr>
                <td>${rankBadge}</td>
                <td><strong>${w.name}</strong></td>
                <td><span class="badge badge-info">Tea Collector</span></td>
                <td>${Math.round(w.original * 10) / 10} kg</td>
                <td style="color: var(--danger); font-weight: 500;">-${Math.round(w.deducted * 10) / 10} kg</td>
                <td style="font-weight: 700; color: var(--primary-light);">${Math.round(w.adjusted * 10) / 10} kg</td>
                <td><span class="badge badge-success">${w.attendance}% (Active)</span></td>
                <td>${efficiencyBadge}</td>
            </tr>
        `;
    });
};

// ==========================================
// 8. SERVANT PERSONAL ACTIVITY BOARD
// ==========================================
const loadServantActivityBoard = () => {
    if (!currentUser || currentUser.role !== 'servant') return;
    
    const weights = tfDb.get(DB_KEYS.WEIGHTS);
    const attendance = tfDb.get(DB_KEYS.ATTENDANCE);
    
    // Filter servant's specific records
    const myWeights = weights.filter(w => w.servant_id === currentUser.user_id).sort((a, b) => b.date.localeCompare(a.date));
    const myAttendance = attendance.filter(a => a.servant_id === currentUser.user_id).sort((a, b) => b.date.localeCompare(a.date));
    
    // 1. Render my personal weighings log
    const weightsBody = document.getElementById('servant-my-weighings');
    weightsBody.innerHTML = '';
    
    if (myWeights.length === 0) {
        weightsBody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-secondary); padding: 20px;">No tea weight records logged for you yet.</td></tr>`;
    } else {
        myWeights.forEach(w => {
            const deduction = w.original_weight - w.adjusted_weight;
            const rainBadge = w.rainy_day ? '<span class="badge badge-danger">Rainy</span>' : '<span class="badge badge-success">Dry</span>';
            weightsBody.innerHTML += `
                <tr>
                    <td>${w.date}</td>
                    <td><strong>${w.area}</strong></td>
                    <td>${w.original_weight} kg</td>
                    <td>${rainBadge}</td>
                    <td style="color: var(--danger); font-weight: 500;">-${deduction.toFixed(2)} kg</td>
                    <td style="font-weight: 700; color: var(--primary-light);">${w.adjusted_weight} kg</td>
                </tr>
            `;
        });
    }
    
    // 2. Render my personal attendance log
    const attBody = document.getElementById('servant-my-attendance');
    attBody.innerHTML = '';
    
    if (myAttendance.length === 0) {
        attBody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-secondary); padding: 20px;">No attendance logs recorded for you.</td></tr>`;
    } else {
        myAttendance.forEach(a => {
            const statusClass = a.status === 'Present' ? 'badge-success' : 'badge-danger';
            attBody.innerHTML += `
                <tr>
                    <td>${a.date}</td>
                    <td>${a.check_in || '--:--'}</td>
                    <td>${a.check_out || '--:--'}</td>
                    <td><span class="badge ${statusClass}">${a.status}</span></td>
                </tr>
            `;
        });
    }
    feather.replace();
};

// ==========================================
// INITIAL SETUP ON LOGGED IN STATUS
// ==========================================
if (currentUser) {
    document.getElementById('auth-view').style.display = 'none';
    document.getElementById('app-shell').style.display = 'grid';
    initializeViewsByRole();
    switchTab('dashboard');
} else {
    document.getElementById('auth-view').style.display = 'flex';
    document.getElementById('app-shell').style.display = 'none';
}
feather.replace();
