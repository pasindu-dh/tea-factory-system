# 🍃 Tea Factory Management System

A high-fidelity, self-contained single-page management portal developed to automate and optimize the daily operations of a tea factory. The system features a premium glassmorphic dark-emerald user interface, dynamic role-based dashboards, and pre-populated mock ledger data for the last 10 days of factory operations.

---

## 🚀 Key Modules & Features

### 🔐 1. Authentication & Role-Based Access Control
- **Owner Dashboard (Main Administrator)**:
  - Add, edit, or remove Field Supervisors and Servant profiles (CRUD).
  - Configure payment rates per kg (tiered by attendance) and daily wages for retail workers.
  - Compute and process 10-day salary runs.
  - Review deep analytics dashboards, leaderboards, and rainy day adjustments.
- **Supervisor Dashboard (Field Operator)**:
  - Register new Servant profiles.
  - Mark daily attendance timecards (automatic "Present/Absent" toggling upon check-in/out logging).
  - Measure and record tea bag weights with real-time **Rainy Day Deductions**.
  - Assign servants daily work areas (Tea fields, processing, packaging).
- **Servant Dashboard (Worker View)**:
  - Interactive SVG attendance progress ring tracking current payroll bracket status.
  - Estimated 10-day salary gauge based on cumulative harvest and attendance category.
  - Personal chronological ledger showing daily weighings and check-in/out timestamps.

### 🌧️ 2. Rainy Day Weight Adjustment System
During rainy days, raw tea leaves absorb moisture, skewing true leaf weight. The system automatically reduces leaf weight at a rate of **1kg per every 20kg** of raw tea:
$$\text{Adjusted Weight} = \text{Original Weight} - \frac{\text{Original Weight}}{20}$$

*   **Example 1**: Raw weight $100\text{ kg} \rightarrow 100 - (100 / 20) = 95\text{ kg}$ final adjusted weight.
*   **Example 2**: Raw weight $50\text{ kg} \rightarrow 50 - (50 / 20) = 47.5\text{ kg}$ final adjusted weight.

### 💰 3. Tiered 10-Day Payroll Engine
Salaries compile every 10 days, applying different rates based on worker attendance percentages:
- **Tea Collectors**: Paid per kilogram collected, depending on attendance bracket:
  - **Attendance > 80%**: Rs. 60 per 1kg
  - **Attendance 70% - 80%**: Rs. 50 per 1kg
  - **Attendance < 70%**: Rs. 40 per 1kg
  $$\text{Salary} = \text{Adjusted Tea Weight} \times \text{Rate Per Kg}$$
- **Retail Workers**: Paid a flat daily rate compiled against presence counts:
  - **Male**: Rs. 2000 / Day
  - **Female**: Rs. 1500 / Day
  $$\text{Salary} = \text{Days Present} \times \text{Daily Wage}$$

---

## 👤 Default Testing Accounts

To log in and experience the interface, use the following pre-registered credentials:

| Role | Name | Phone Number | Password | Features Accessible |
| :--- | :--- | :--- | :--- | :--- |
| **Owner** | Aruna Perera | `0771112222` | `owner123` | Full CRUD, Salary Run, Configuration, Charts |
| **Supervisor** | Kamal Silva | `0773334444` | `super123` | Mark Attendance, Assign Areas, Record Weights |
| **Servant (Collector)** | Kusal Mendis | `0777778888` | `servant123` | Personal weights ledger, Attendance ring, Salary Estimator |
| **Servant (Retail)** | Chamari Athapaththu | `0774445555` | `servant123` | Retail wages policy indicator, Attendance log |

---

## 🛠️ Technology Stack
- **Structure**: Semantic HTML5 markup.
- **Styling**: Vanilla CSS3 custom property grid, responsive media queries, glassmorphism filters, and micro-interaction scale triggers.
- **Logic**: ES6+ JavaScript modules.
- **Simulated Database**: Persistent client-side database utilizing `localStorage` initialized with 10 days of historical timelines.
- **Vector Icons**: Feather Icons via CDN.
- **Reporting Engine**: Chart.js canvas graph animations.

---

## 💻 Running the Portal Locally

The system runs entirely in the browser with **zero local setup requirements** (no local database servers, python packages, or node installations required).

### Method A: Direct Browser Load
1. Double-click [index.html](index.html) or drag it into any modern web browser (Chrome, Edge, Firefox, Safari).

### Method B: Via Local Dev Server (Recommended)
To prevent browser sandbox warnings and enable high-fidelity font loading, launch a quick static server:

*   **Using Python (Pre-installed on macOS/Windows)**:
    ```powershell
    # Open terminal in project folder and run:
    python -m http.server 8000
    ```
    Then visit `http://localhost:8000` in your web browser.

*   **Using Node.js (npx serve)**:
    ```powershell
    # Open terminal in project folder and run:
    npx -y serve
    ```
    Then visit the local address displayed in the terminal.

---

## 📂 Project Directory Structure

```text
Tea Factory/
│
├── index.html       # Primary layout, sidebars, dashboard grids, and forms
├── index.css        # Premium custom stylesheet, fonts, badges, variables, widgets
├── app.js           # Database, state manager, auth controller, formulas, payroll run
├── tea_bg.png       # Cinematic wide background banner of tea estate
└── README.md        # Technical portal manuals (This file)
```
