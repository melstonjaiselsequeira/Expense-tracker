// ══════════════════════════════════════════════════════════════════
// ExpenseFlow — Enhanced Application Logic
// ══════════════════════════════════════════════════════════════════

const API = '/api';

const CATEGORIES = {
  Food:          { icon: 'fa-utensils',       color: '#f97316' },
  Transport:     { icon: 'fa-car',            color: '#3b82f6' },
  Shopping:      { icon: 'fa-bag-shopping',   color: '#ec4899' },
  Bills:         { icon: 'fa-file-invoice',   color: '#eab308' },
  Entertainment: { icon: 'fa-film',           color: '#8b5cf6' },
  Health:        { icon: 'fa-heartbeat',      color: '#10b981' },
  Education:     { icon: 'fa-graduation-cap', color: '#06b6d4' },
  Other:         { icon: 'fa-box',            color: '#64748b' }
};

let trendChart = null;
let categoryChart = null;
let deleteTargetId = null;
let currentExpensesList = [];
let lastDailyTrendData = null;
let lastCategoryBreakdownData = null;

// ── DOM Helpers ────────────────────────────────────────────────
function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }

function formatCurrency(n) {
  const num = Number(n) || 0;
  return '$' + num.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

function formatDate(dateStr) {
  if (!dateStr) return '—';
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function showToast(message, type = 'success') {
  const container = $('#toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  const icons = {
    success: 'fa-check-circle',
    error: 'fa-exclamation-circle',
    info: 'fa-info-circle'
  };
  toast.innerHTML = `<i class="fas ${icons[type] || 'fa-info-circle'}"></i> <span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.animation = 'slideOut .3s forwards';
    setTimeout(() => toast.remove(), 300);
  }, 3200);
}

// ── Theme Management ───────────────────────────────────────────
let lastThemeToggle = 0;

function getActiveTheme() {
  return document.documentElement.getAttribute('data-theme') ||
         localStorage.getItem('expenseflow_theme') ||
         'dark';
}

function toggleTheme() {
  const now = Date.now();
  if (now - lastThemeToggle < 300) return; // Prevent double-execution from bubbling / rapid clicks
  lastThemeToggle = now;

  const current = getActiveTheme();
  const next = current === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  localStorage.setItem('expenseflow_theme', next);
  showToast(`Switched to ${next === 'light' ? 'Light' : 'Dark'} mode`, 'info');
}
window.toggleTheme = toggleTheme;

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  if (document.body) {
    document.body.setAttribute('data-theme', theme);
  }

  const icon = document.getElementById('theme-icon');
  const label = document.getElementById('theme-label');
  const chip = document.getElementById('theme-status-chip');

  if (theme === 'light') {
    if (icon) icon.className = 'fas fa-sun';
    if (label) label.textContent = 'Light Mode';
    if (chip) chip.textContent = 'Light';
  } else {
    if (icon) icon.className = 'fas fa-moon';
    if (label) label.textContent = 'Dark Mode';
    if (chip) chip.textContent = 'Dark';
  }

  // Refresh charts with theme-appropriate grid and text colors
  try {
    if (typeof Chart !== 'undefined') {
      if (typeof lastDailyTrendData !== 'undefined' && lastDailyTrendData) renderTrendChart(lastDailyTrendData);
      if (typeof lastCategoryBreakdownData !== 'undefined' && lastCategoryBreakdownData) renderCategoryChart(lastCategoryBreakdownData);
    }
  } catch (err) {
    console.warn('Chart refresh on theme change failed:', err);
  }
}

function initTheme() {
  const saved = localStorage.getItem('expenseflow_theme');
  const theme = saved || 'dark';
  applyTheme(theme);
}

// Global click listener for theme toggle button (ensures clicks always register)
document.addEventListener('click', e => {
  const toggleBtn = e.target && e.target.closest('#btn-theme-toggle, .btn-theme-toggle');
  if (toggleBtn) {
    e.preventDefault();
    toggleTheme();
  }
});

// Run theme init immediately
initTheme();

// ── Navigation ─────────────────────────────────────────────────
function switchView(viewName) {
  $$('.view').forEach(v => v.classList.remove('active'));
  $$('.nav-item').forEach(n => n.classList.remove('active'));
  
  const targetView = $(`#view-${viewName}`);
  const targetNav = $(`[data-view="${viewName}"]`);
  
  if (targetView) targetView.classList.add('active');
  if (targetNav) targetNav.classList.add('active');

  window.scrollTo({ top: 0, behavior: 'instant' });
  closeMobileSidebar();

  if (viewName === 'dashboard') {
    loadDashboard();
  } else {
    loadExpenses();
  }
}

$$('.nav-item').forEach(item => {
  item.addEventListener('click', e => {
    e.preventDefault();
    switchView(item.dataset.view);
  });
});

const viewAllLink = $('#view-all-link');
if (viewAllLink) {
  viewAllLink.addEventListener('click', e => {
    e.preventDefault();
    switchView('expenses');
  });
}

// Mobile sidebar controls
const menuToggle = $('#menu-toggle');
const sidebarOverlay = $('#sidebar-overlay');
const sidebar = $('#sidebar');

function openMobileSidebar() {
  if (sidebar) sidebar.classList.add('open');
  if (sidebarOverlay) sidebarOverlay.classList.add('active');
}

function closeMobileSidebar() {
  if (sidebar) sidebar.classList.remove('open');
  if (sidebarOverlay) sidebarOverlay.classList.remove('active');
}

if (menuToggle) menuToggle.addEventListener('click', openMobileSidebar);
if (sidebarOverlay) sidebarOverlay.addEventListener('click', closeMobileSidebar);

const btnAddMobile = $('#btn-add-mobile');
if (btnAddMobile) btnAddMobile.addEventListener('click', () => openModal());

// Top action buttons
const btnTopAdd = $('#btn-top-add');
if (btnTopAdd) btnTopAdd.addEventListener('click', () => openModal());

const btnTopShortcuts = $('#btn-top-shortcuts');
if (btnTopShortcuts) btnTopShortcuts.addEventListener('click', openShortcutsModal);

// ── Budget Goal Logic ──────────────────────────────────────────
let currentUserBudget = 1000;
try { localStorage.removeItem('expenseflow_budget'); } catch (e) {}

function getMonthlyBudget() {
  return (typeof currentUserBudget === 'number' && currentUserBudget > 0) ? currentUserBudget : 1000;
}

async function setMonthlyBudget(amount) {
  currentUserBudget = amount;
  try {
    const res = await fetch(`${API}/budget`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ monthly_budget: amount })
    });
    if (!res.ok) throw new Error('Failed to save budget');
    const data = await res.json();
    if (data && data.monthly_budget !== undefined) {
      currentUserBudget = Number(data.monthly_budget);
    }
  } catch (err) {
    console.warn('Could not persist budget to server:', err);
  }
}

function updateBudgetUI(monthlySpent) {
  const budget = getMonthlyBudget();
  const spent = Number(monthlySpent) || 0;
  const remaining = Math.max(0, budget - spent);
  const percent = budget > 0 ? (spent / budget) * 100 : 0;
  const clampedPercent = Math.min(100, Math.max(0, percent));

  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  const currentDay = now.getDate();
  const totalDaysInMonth = new Date(year, month + 1, 0).getDate();
  const daysRemaining = Math.max(1, totalDaysInMonth - currentDay);
  const elapsedDays = currentDay;

  // Daily Allowance Calculation
  const dailyAllowance = daysRemaining > 0 ? (remaining / daysRemaining) : 0;

  // Algorithmic Pacing vs Planned Run Rate
  const expectedPaceSpent = (budget / totalDaysInMonth) * elapsedDays;
  const paceDifference = expectedPaceSpent - spent;

  const limitEl = $('#budget-limit-val');
  const spentEl = $('#budget-spent-val');
  const remainEl = $('#budget-remaining-val');
  const percentSub = $('#budget-percent-sub');
  const fillBar = $('#budget-progress-fill');
  const badge = $('#budget-status-badge');
  const monthLabel = $('#budget-month-label');
  const dailyAllowanceEl = $('#budget-daily-allowance');
  const daysLeftSub = $('#budget-days-left-sub');

  if (monthLabel) {
    const monthName = now.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
    monthLabel.textContent = `${monthName} (${elapsedDays} of ${totalDaysInMonth} days elapsed)`;
  }

  if (limitEl) limitEl.textContent = formatCurrency(budget);
  if (spentEl) spentEl.textContent = formatCurrency(spent);
  if (remainEl) remainEl.textContent = formatCurrency(remaining);
  if (percentSub) percentSub.textContent = `${percent.toFixed(1)}% of budget used`;

  if (dailyAllowanceEl) {
    dailyAllowanceEl.textContent = `${formatCurrency(dailyAllowance)} / day`;
  }
  if (daysLeftSub) {
    daysLeftSub.textContent = `${daysRemaining} day${daysRemaining === 1 ? '' : 's'} remaining`;
  }

  if (fillBar) {
    fillBar.style.width = `${clampedPercent}%`;
    fillBar.className = 'budget-progress-fill';
    if (percent >= 100) {
      fillBar.classList.add('danger');
    } else if (percent >= 80) {
      fillBar.classList.add('warning');
    }
  }

  if (badge) {
    badge.className = 'budget-badge';
    if (percent >= 100) {
      badge.classList.add('danger');
      badge.textContent = `Over Budget by ${formatCurrency(spent - budget)}`;
    } else if (percent >= 80) {
      badge.classList.add('warning');
      badge.textContent = `Warning: ${percent.toFixed(0)}% Used`;
    } else {
      badge.classList.add('normal');
      badge.textContent = `${percent.toFixed(1)}% Utilized • On Track`;
    }
  }

  // Update Pacing Recommendations
  const paceTitleEl = $('#pacing-title-pace');
  const paceDescEl = $('#pacing-desc-pace');
  const paceIconEl = $('#pacing-icon-pace');

  if (paceTitleEl && paceDescEl && paceIconEl) {
    if (spent > budget) {
      paceIconEl.innerHTML = '<i class="fas fa-circle-xmark" style="color: var(--danger);"></i>';
      paceTitleEl.textContent = 'Budget Exceeded:';
      paceDescEl.textContent = `You have surpassed your planned monthly ceiling by ${formatCurrency(spent - budget)}.`;
    } else if (paceDifference >= 0) {
      paceIconEl.innerHTML = '<i class="fas fa-circle-check" style="color: var(--success);"></i>';
      paceTitleEl.textContent = 'Spending Under Ceiling:';
      paceDescEl.textContent = `You are currently ${formatCurrency(paceDifference)} under your planned ${elapsedDays}-day run rate.`;
    } else {
      paceIconEl.innerHTML = '<i class="fas fa-triangle-exclamation" style="color: var(--warning);"></i>';
      paceTitleEl.textContent = 'Pacing Above Target:';
      paceDescEl.textContent = `You are running ${formatCurrency(Math.abs(paceDifference))} ahead of your planned ${elapsedDays}-day pace.`;
    }
  }

  const daysTitleEl = $('#pacing-title-days');
  const daysDescEl = $('#pacing-desc-days');
  if (daysTitleEl && daysDescEl) {
    daysTitleEl.textContent = `${daysRemaining} Days Remaining:`;
    if (remaining <= 0) {
      daysDescEl.textContent = 'Zero budget remaining for the rest of this month. Consider adjusting limit.';
    } else {
      daysDescEl.textContent = `Allocating up to ${formatCurrency(dailyAllowance)}/day will keep you safely within your monthly target.`;
    }
  }
}

// ── Top Greeting Date ──────────────────────────────────────────
function updateTopGreeting() {
  const dateEl = document.getElementById('current-date-text');
  const greetingEl = document.getElementById('greeting-text');
  const now = new Date();

  if (dateEl) {
    dateEl.textContent = now.toLocaleDateString('en-US', {
      weekday: 'long',
      month: 'long',
      day: 'numeric',
      year: 'numeric'
    });
  }

  if (greetingEl) {
    const hours = now.getHours();
    let timeGreeting = 'Good morning';
    if (hours >= 12 && hours < 17) timeGreeting = 'Good afternoon';
    else if (hours >= 17) timeGreeting = 'Good evening';
    
    // Check if greetingEl has user name
    const userNameEl = document.getElementById('sidebar-user-name');
    const name = (userNameEl && userNameEl.textContent.trim()) || 'there';
    greetingEl.innerHTML = `${timeGreeting}, ${name}! 👋`;
  }
}
window.updateTopGreeting = updateTopGreeting;

// Call immediately so date displays instantly
updateTopGreeting();

// ── Dashboard Data ─────────────────────────────────────────────
async function loadDashboard() {
  updateTopGreeting();
  try {
    const res = await fetch(`${API}/stats`);
    if (!res.ok) throw new Error('Failed to fetch stats');
    const stats = await res.json();

    $('#stat-total-value').textContent = formatCurrency(stats.total);
    $('#stat-monthly-value').textContent = formatCurrency(stats.monthly);
    $('#stat-daily-value').textContent = formatCurrency(stats.daily_avg);
    $('#stat-top-value').textContent = stats.top_category || '—';

    const plannedEl = $('#stat-monthly-planned');
    if (plannedEl) {
      if (stats.planned_monthly && stats.planned_monthly > 0) {
        plannedEl.textContent = `Planned: ${formatCurrency(stats.planned_monthly)}`;
        plannedEl.style.display = 'block';
      } else {
        plannedEl.style.display = 'none';
      }
    }

    if (stats.monthly_budget !== undefined && stats.monthly_budget !== null) {
      currentUserBudget = Number(stats.monthly_budget);
    }
    updateBudgetUI(stats.monthly);

    lastDailyTrendData = stats.daily_trend;
    lastCategoryBreakdownData = stats.category_breakdown;

    renderTrendChart(stats.daily_trend);
    renderCategoryChart(stats.category_breakdown);
    loadRecentExpenses();
  } catch (err) {
    showToast('Failed to load dashboard data', 'error');
  }
}

function renderTrendChart(data) {
  const chartCanvas = $('#trendChart');
  if (!chartCanvas) return;
  const ctx = chartCanvas.getContext('2d');
  const labels = Object.keys(data || {}).map(d => {
    const date = new Date(d + 'T00:00:00');
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  });
  const values = Object.values(data || {});

  if (trendChart) trendChart.destroy();

  const isLight = document.documentElement.getAttribute('data-theme') === 'light';
  const gridColor = isLight ? 'rgba(0, 0, 0, 0.06)' : 'rgba(255, 255, 255, 0.05)';
  const tickColor = isLight ? '#64748b' : '#94a3b8';
  const tooltipBg = isLight ? 'rgba(255, 255, 255, 0.95)' : 'rgba(17, 24, 39, 0.95)';
  const tooltipTitle = isLight ? '#0f172a' : '#f1f5f9';
  const tooltipBorder = isLight ? '#cbd5e1' : 'rgba(255, 255, 255, 0.12)';

  const gradient = ctx.createLinearGradient(0, 0, 0, 260);
  gradient.addColorStop(0, isLight ? 'rgba(124, 58, 237, 0.28)' : 'rgba(139, 92, 246, 0.32)');
  gradient.addColorStop(1, 'rgba(139, 92, 246, 0.0)');

  trendChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Daily Spending',
        data: values,
        borderColor: isLight ? '#7c3aed' : '#8b5cf6',
        backgroundColor: gradient,
        borderWidth: 2.5,
        fill: true,
        tension: 0.35,
        pointRadius: 1,
        pointHoverRadius: 6,
        pointHoverBackgroundColor: '#8b5cf6',
        pointHoverBorderColor: '#ffffff',
        pointHoverBorderWidth: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: tooltipBg,
          titleColor: tooltipTitle,
          bodyColor: '#64748b',
          borderColor: tooltipBorder,
          borderWidth: 1,
          padding: 12,
          displayColors: false,
          callbacks: {
            label: c => `Spending: ${formatCurrency(c.raw)}`
          }
        }
      },
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: { color: tickColor, font: { size: 10 }, maxTicksLimit: 8 }
        },
        y: {
          grid: { color: gridColor },
          ticks: {
            color: tickColor,
            font: { size: 10 },
            callback: v => '$' + v
          }
        }
      }
    }
  });
}

function renderCategoryChart(data) {
  const chartCanvas = $('#categoryChart');
  if (!chartCanvas) return;
  const ctx = chartCanvas.getContext('2d');
  const labels = Object.keys(data || {});
  const values = Object.values(data || {});
  const colors = labels.map(l => CATEGORIES[l]?.color || '#64748b');

  if (categoryChart) categoryChart.destroy();

  const isLight = document.documentElement.getAttribute('data-theme') === 'light';
  const tooltipBg = isLight ? 'rgba(255, 255, 255, 0.95)' : 'rgba(17, 24, 39, 0.95)';
  const tooltipTitle = isLight ? '#0f172a' : '#f1f5f9';
  const borderColor = isLight ? '#ffffff' : 'rgba(17, 24, 39, 0.9)';

  categoryChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: colors,
        borderColor: borderColor,
        borderWidth: 3,
        hoverOffset: 8
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '68%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            color: isLight ? '#475569' : '#94a3b8',
            padding: 14,
            font: { size: 11, family: 'Inter' },
            usePointStyle: true,
            pointStyleWidth: 8
          }
        },
        tooltip: {
          backgroundColor: tooltipBg,
          titleColor: tooltipTitle,
          bodyColor: '#64748b',
          borderColor: isLight ? '#cbd5e1' : 'rgba(255, 255, 255, 0.1)',
          borderWidth: 1,
          padding: 12,
          callbacks: {
            label: c => `${c.label}: ${formatCurrency(c.raw)}`
          }
        }
      }
    }
  });
}

async function loadRecentExpenses() {
  try {
    const res = await fetch(`${API}/expenses?sort=date_desc`);
    const expenses = await res.json();
    const recent = expenses.slice(0, 5);
    const list = $('#recent-list');
    if (!list) return;

    if (recent.length === 0) {
      list.innerHTML = `
        <div class="empty-state">
          <i class="fas fa-receipt"></i>
          <p>No expenses recorded yet.</p>
        </div>`;
      return;
    }

    list.innerHTML = recent.map(e => {
      const cat = CATEGORIES[e.category] || CATEGORIES.Other;
      const isPlanned = (e.status || 'paid') === 'planned';
      const statusBadge = isPlanned
        ? `<span class="status-badge planned" style="margin-left:6px;padding:2px 7px;font-size:0.68rem;"><i class="fas fa-clock"></i> Planned</span>`
        : '';
      const payQuick = isPlanned
        ? `<button class="btn-icon pay" onclick="markAsPaid(${e.id})" title="Mark as Paid" style="width:28px;height:28px;font-size:0.75rem;margin-left:8px;"><i class="fas fa-check"></i></button>`
        : '';
      const amountColor = isPlanned ? 'color: #f59e0b;' : '';
      return `
        <div class="recent-item">
          <div class="recent-item-icon" style="background:${cat.color}20; color:${cat.color}">
            <i class="fas ${cat.icon}"></i>
          </div>
          <div class="recent-item-info">
            <div class="recent-item-desc">${escapeHtml(e.description)}${statusBadge}</div>
            <div class="recent-item-date">${formatDate(e.date)} · ${escapeHtml(e.category)}</div>
          </div>
          <div style="display:flex;align-items:center;">
            <div class="recent-item-amount" style="${amountColor}">-${formatCurrency(e.amount)}</div>
            ${payQuick}
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    console.error('Failed to load recent expenses:', err);
  }
}

// ── Expenses List & Table ──────────────────────────────────────
async function loadExpenses() {
  try {
    const params = new URLSearchParams();
    const cat = $('#filter-category').value;
    const search = $('#search-input').value.trim();
    const startDate = $('#filter-start-date').value;
    const endDate = $('#filter-end-date').value;
    const sort = $('#filter-sort').value;
    const statusSelect = $('#filter-status');
    const statusVal = statusSelect ? statusSelect.value : 'all';

    if (cat && cat !== 'All') params.append('category', cat);
    if (search) params.append('search', search);
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    if (sort) params.append('sort', sort);
    if (statusVal && statusVal !== 'all') params.append('status', statusVal);

    const res = await fetch(`${API}/expenses?${params}`);
    if (!res.ok) throw new Error('Failed to load expenses');
    currentExpensesList = await res.json();

    renderExpensesTable(currentExpensesList);
    updateSummaryStrip(currentExpensesList);
  } catch (err) {
    showToast('Failed to load expenses', 'error');
  }
}

function updateSummaryStrip(expenses) {
  const paidExpenses = expenses.filter(e => (e.status || 'paid') === 'paid');
  const plannedExpenses = expenses.filter(e => (e.status || 'paid') === 'planned');
  const total = paidExpenses.reduce((s, e) => s + (Number(e.amount) || 0), 0);
  const count = paidExpenses.length;
  const avg = count > 0 ? total / count : 0;

  const totalEl = $('#summary-filtered-total');
  const countEl = $('#summary-filtered-count');
  const avgEl = $('#summary-filtered-avg');

  if (totalEl) totalEl.textContent = formatCurrency(total);
  if (countEl) countEl.textContent = `${count.toLocaleString()}${plannedExpenses.length > 0 ? ` (+${plannedExpenses.length} planned)` : ''}`;
  if (avgEl) avgEl.textContent = formatCurrency(avg);
}

function renderExpensesTable(expenses) {
  const tbody = $('#expenses-tbody');
  if (!tbody) return;

  if (expenses.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6">
          <div class="empty-state">
            <i class="fas fa-receipt"></i>
            <p>No expenses match your search or filter criteria.</p>
            <button class="btn-primary" onclick="openModal()">
              <i class="fas fa-plus"></i> Add New Expense
            </button>
          </div>
        </td>
      </tr>`;
    $('#table-info').textContent = 'Showing 0 records';
    $('#table-total').textContent = 'Total: $0.00';
    return;
  }

  const paidExpenses = expenses.filter(e => (e.status || 'paid') === 'paid');
  const plannedExpenses = expenses.filter(e => (e.status || 'paid') === 'planned');
  const paidTotal = paidExpenses.reduce((s, e) => s + (Number(e.amount) || 0), 0);
  const plannedTotal = plannedExpenses.reduce((s, e) => s + (Number(e.amount) || 0), 0);

  tbody.innerHTML = expenses.map(e => {
    const cat = CATEGORIES[e.category] || CATEGORIES.Other;
    const catClass = (e.category || 'other').toLowerCase();
    const isPlanned = (e.status || 'paid') === 'planned';
    const statusBadge = isPlanned
      ? `<span class="status-badge planned"><i class="fas fa-clock"></i> Planned</span>`
      : `<span class="status-badge paid"><i class="fas fa-check-circle"></i> Paid</span>`;
    const payBtn = isPlanned
      ? `<button class="btn-icon pay" onclick="markAsPaid(${e.id})" title="Mark as Paid"><i class="fas fa-check"></i></button>`
      : '';
    const amountClass = isPlanned ? 'amount-cell planned' : 'amount-cell';

    return `
      <tr>
        <td><strong>${formatDate(e.date)}</strong></td>
        <td>
          <span class="category-badge ${catClass}">
            <i class="fas ${cat.icon}"></i> ${escapeHtml(e.category)}
          </span>
        </td>
        <td><span title="${escapeHtml(e.description)}">${escapeHtml(e.description)}</span></td>
        <td>${statusBadge}</td>
        <td class="${amountClass}">-${formatCurrency(e.amount)}</td>
        <td style="text-align: right;">
          <div class="action-btns" style="justify-content: flex-end;">
            ${payBtn}
            <button class="btn-icon edit" onclick="editExpense(${e.id})" title="Edit Expense">
              <i class="fas fa-pen"></i>
            </button>
            <button class="btn-icon duplicate" onclick="duplicateExpense(${e.id})" title="Duplicate Expense">
              <i class="fas fa-copy"></i>
            </button>
            <button class="btn-icon delete" onclick="confirmDelete(${e.id})" title="Delete Expense">
              <i class="fas fa-trash"></i>
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join('');

  $('#table-info').textContent = `Showing ${expenses.length} record${expenses.length > 1 ? 's' : ''}`;
  if (plannedTotal > 0) {
    $('#table-total').innerHTML = `Paid: <strong>${formatCurrency(paidTotal)}</strong> <span style="font-size:0.85rem;color:#f59e0b;margin-left:0.5rem;">(Planned: ${formatCurrency(plannedTotal)})</span>`;
  } else {
    $('#table-total').textContent = `Total: ${formatCurrency(paidTotal)}`;
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ── Filter Controls & Listeners ────────────────────────────────
let filterTimeout;
const searchInput = $('#search-input');
const btnClearSearch = $('#btn-clear-search');

if (searchInput) {
  searchInput.addEventListener('input', () => {
    if (btnClearSearch) {
      btnClearSearch.style.display = searchInput.value ? 'block' : 'none';
    }
    clearTimeout(filterTimeout);
    filterTimeout = setTimeout(loadExpenses, 280);
  });
}

if (btnClearSearch) {
  btnClearSearch.addEventListener('click', () => {
    searchInput.value = '';
    btnClearSearch.style.display = 'none';
    loadExpenses();
    searchInput.focus();
  });
}

// Category Pills interaction
$$('.category-pill').forEach(pill => {
  pill.addEventListener('click', () => {
    $$('.category-pill').forEach(p => p.classList.remove('active'));
    pill.classList.add('active');
    const cat = pill.dataset.category || 'All';
    const select = $('#filter-category');
    if (select) select.value = cat;
    loadExpenses();
  });
});

// Category Select dropdown (sync with pills)
const filterCategory = $('#filter-category');
if (filterCategory) {
  filterCategory.addEventListener('change', () => {
    const cat = filterCategory.value;
    $$('.category-pill').forEach(p => {
      p.classList.toggle('active', p.dataset.category === cat);
    });
    loadExpenses();
  });
}

const filterStatus = $('#filter-status');
if (filterStatus) {
  filterStatus.addEventListener('change', loadExpenses);
}

// Date Presets
$$('.btn-preset').forEach(btn => {
  btn.addEventListener('click', () => {
    $$('.btn-preset').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    const preset = btn.dataset.preset;
    const startInput = $('#filter-start-date');
    const endInput = $('#filter-end-date');
    const now = new Date();

    if (preset === 'all') {
      startInput.value = '';
      endInput.value = '';
    } else if (preset === 'this-month') {
      const year = now.getFullYear();
      const month = String(now.getMonth() + 1).padStart(2, '0');
      startInput.value = `${year}-${month}-01`;
      endInput.value = now.toISOString().split('T')[0];
    } else if (preset === 'last-30') {
      const past = new Date(now.getTime() - 30 * 24 * 60 * 1000);
      startInput.value = past.toISOString().split('T')[0];
      endInput.value = now.toISOString().split('T')[0];
    } else if (preset === 'this-year') {
      const year = now.getFullYear();
      startInput.value = `${year}-01-01`;
      endInput.value = now.toISOString().split('T')[0];
    }

    loadExpenses();
  });
});

// Reset Filters Button
const btnResetFilters = $('#btn-reset-filters');
if (btnResetFilters) {
  btnResetFilters.addEventListener('click', () => {
    if (searchInput) searchInput.value = '';
    if (btnClearSearch) btnClearSearch.style.display = 'none';
    if (filterCategory) filterCategory.value = 'All';
    if (filterStatus) filterStatus.value = 'all';
    $('#filter-start-date').value = '';
    $('#filter-end-date').value = '';
    $('#filter-sort').value = 'date_desc';

    $$('.category-pill').forEach(p => p.classList.toggle('active', p.dataset.category === 'All'));
    $$('.btn-preset').forEach(b => b.classList.toggle('active', b.dataset.preset === 'all'));

    loadExpenses();
    showToast('Filters reset', 'info');
  });
}

$('#filter-start-date').addEventListener('change', () => {
  $$('.btn-preset').forEach(b => b.classList.remove('active'));
  loadExpenses();
});
$('#filter-end-date').addEventListener('change', () => {
  $$('.btn-preset').forEach(b => b.classList.remove('active'));
  loadExpenses();
});
$('#filter-sort').addEventListener('change', loadExpenses);

// Clickable Sort Headers on Table
$$('.expenses-table th.sortable').forEach(th => {
  th.addEventListener('click', () => {
    const field = th.dataset.sortField;
    const currentSort = $('#filter-sort').value;
    let nextSort = `${field}_desc`;

    if (currentSort === `${field}_desc`) {
      nextSort = `${field}_asc`;
    } else {
      nextSort = `${field}_desc`;
    }

    const select = $('#filter-sort');
    if (select) {
      select.value = nextSort;
      loadExpenses();
    }
  });
});

// ── Modals Management ──────────────────────────────────────────
function openModal(expense = null) {
  const overlay = $('#modal-overlay');
  const form = $('#expense-form');
  form.reset();
  $('#expense-id').value = '';

  if (expense) {
    $('#modal-title').innerHTML = '<i class="fas fa-edit"></i> Edit Expense';
    $('#btn-save').innerHTML = '<i class="fas fa-check"></i> Update Expense';
    $('#expense-id').value = expense.id;
    $('#expense-amount').value = expense.amount;
    $('#expense-description').value = expense.description;
    $('#expense-date').value = expense.date;
    const radio = document.querySelector(`input[name="category"][value="${expense.category}"]`);
    if (radio) radio.checked = true;
    const statusVal = expense.status || 'paid';
    const statusRadio = document.querySelector(`input[name="expense-status"][value="${statusVal}"]`);
    if (statusRadio) statusRadio.checked = true;
  } else {
    $('#modal-title').innerHTML = '<i class="fas fa-plus-circle"></i> Add Expense';
    $('#btn-save').innerHTML = '<i class="fas fa-check"></i> Save Expense';
    $('#expense-date').value = new Date().toISOString().split('T')[0];
    const defaultRadio = document.querySelector('input[name="category"][value="Food"]');
    if (defaultRadio) defaultRadio.checked = true;
    const defaultStatusRadio = document.querySelector('input[name="expense-status"][value="paid"]');
    if (defaultStatusRadio) defaultStatusRadio.checked = true;
  }

  overlay.classList.add('active');
  setTimeout(() => $('#expense-amount').focus(), 150);
}

// Auto-suggest "Planned" when selecting future date on new expense
const expenseDateInput = $('#expense-date');
if (expenseDateInput) {
  expenseDateInput.addEventListener('change', () => {
    if (!$('#expense-id').value) {
      const todayStr = new Date().toISOString().split('T')[0];
      const selected = expenseDateInput.value;
      if (selected > todayStr) {
        const plannedRadio = document.querySelector('input[name="expense-status"][value="planned"]');
        if (plannedRadio) plannedRadio.checked = true;
      } else {
        const paidRadio = document.querySelector('input[name="expense-status"][value="paid"]');
        if (paidRadio) paidRadio.checked = true;
      }
    }
  });
}

function closeModal() {
  $('#modal-overlay').classList.remove('active');
}

const modalClose = $('#modal-close');
if (modalClose) modalClose.addEventListener('click', closeModal);
const btnCancel = $('#btn-cancel');
if (btnCancel) btnCancel.addEventListener('click', closeModal);
const modalOverlay = $('#modal-overlay');
if (modalOverlay) {
  modalOverlay.addEventListener('click', e => {
    if (e.target === e.currentTarget) closeModal();
  });
}

// Trigger add modal buttons
const btnAddExpense = $('#btn-add-expense');
if (btnAddExpense) btnAddExpense.addEventListener('click', () => openModal());
const btnAddExpense2 = $('#btn-add-expense-2');
if (btnAddExpense2) btnAddExpense2.addEventListener('click', () => openModal());

// Form Submit (Add or Edit)
$('#expense-form').addEventListener('submit', async e => {
  e.preventDefault();

  const id = $('#expense-id').value;
  const categoryRadio = document.querySelector('input[name="category"]:checked');
  const statusRadio = document.querySelector('input[name="expense-status"]:checked');

  if (!categoryRadio) {
    showToast('Please select a category', 'error');
    return;
  }

  const expStatus = statusRadio ? statusRadio.value : 'paid';

  const data = {
    amount: parseFloat($('#expense-amount').value),
    category: categoryRadio.value,
    description: $('#expense-description').value.trim(),
    date: $('#expense-date').value,
    status: expStatus
  };

  if (!data.amount || data.amount <= 0) {
    showToast('Please enter a valid amount greater than $0', 'error');
    return;
  }
  if (!data.description) {
    showToast('Please enter a description', 'error');
    return;
  }

  try {
    const url = id ? `${API}/expenses/${id}` : `${API}/expenses`;
    const method = id ? 'PUT' : 'POST';

    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });

    if (!res.ok) throw new Error('Failed to save expense');

    closeModal();
    const isPlanned = expStatus === 'planned';
    showToast(
      id
        ? 'Expense updated successfully!'
        : isPlanned
        ? 'Planned expense scheduled! (Will not affect spending until paid)'
        : 'Expense added successfully!',
      'success'
    );
    loadDashboard();
    loadExpenses();
  } catch (err) {
    showToast('Failed to save expense. Please try again.', 'error');
  }
});

// Mark as Paid Global Handler (Converts planned to paid in-place without duplicate)
window.markAsPaid = async function(id) {
  try {
    const res = await fetch(`${API}/expenses/${id}/mark-paid`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    if (!res.ok) throw new Error('Failed to mark expense as paid');
    showToast('Expense marked as paid! Added to actual spending.', 'success');
    loadDashboard();
    loadExpenses();
  } catch (err) {
    showToast('Failed to mark expense as paid. Please try again.', 'error');
  }
};

// Edit & Duplicate Global Handlers
window.editExpense = async function(id) {
  try {
    const res = await fetch(`${API}/expenses`);
    const expenses = await res.json();
    const expense = expenses.find(e => e.id === id);
    if (expense) openModal(expense);
  } catch (err) {
    showToast('Failed to load expense details', 'error');
  }
};

window.duplicateExpense = async function(id) {
  try {
    const res = await fetch(`${API}/expenses`);
    const expenses = await res.json();
    const expense = expenses.find(e => e.id === id);
    if (expense) {
      // Open modal with same description and amount, but new entry for today
      openModal({
        id: '',
        amount: expense.amount,
        category: expense.category,
        description: expense.description,
        date: new Date().toISOString().split('T')[0],
        status: 'paid'
      });
      $('#modal-title').innerHTML = '<i class="fas fa-copy"></i> Duplicate Expense';
      $('#btn-save').innerHTML = '<i class="fas fa-check"></i> Save Copy';
      showToast('Duplicating expense. Review and save.', 'info');
    }
  } catch (err) {
    showToast('Failed to duplicate expense', 'error');
  }
};

// ── Delete Modal ───────────────────────────────────────────────
window.confirmDelete = function(id) {
  deleteTargetId = id;
  $('#delete-modal-overlay').classList.add('active');
};

function closeDeleteModal() {
  $('#delete-modal-overlay').classList.remove('active');
  deleteTargetId = null;
}

const deleteModalClose = $('#delete-modal-close');
if (deleteModalClose) deleteModalClose.addEventListener('click', closeDeleteModal);
const btnCancelDelete = $('#btn-cancel-delete');
if (btnCancelDelete) btnCancelDelete.addEventListener('click', closeDeleteModal);
const deleteModalOverlay = $('#delete-modal-overlay');
if (deleteModalOverlay) {
  deleteModalOverlay.addEventListener('click', e => {
    if (e.target === e.currentTarget) closeDeleteModal();
  });
}

$('#btn-confirm-delete').addEventListener('click', async () => {
  if (!deleteTargetId) return;
  try {
    const res = await fetch(`${API}/expenses/${deleteTargetId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete');

    closeDeleteModal();
    showToast('Expense deleted successfully!', 'success');
    loadDashboard();
    loadExpenses();
  } catch (err) {
    showToast('Failed to delete expense', 'error');
  }
});

// ── Budget Modal ───────────────────────────────────────────────
function openBudgetModal() {
  const overlay = $('#budget-modal-overlay');
  if (!overlay) return;
  const current = getMonthlyBudget();
  const input = $('#budget-input-amount');
  if (input) input.value = current;
  overlay.classList.add('active');
  setTimeout(() => {
    const inp = $('#budget-input-amount');
    if (inp) inp.focus();
  }, 150);
}

function closeBudgetModal() {
  const overlay = $('#budget-modal-overlay');
  if (overlay) overlay.classList.remove('active');
}
window.openBudgetModal = openBudgetModal;
window.closeBudgetModal = closeBudgetModal;

const btnEditBudget = $('#btn-edit-budget');
if (btnEditBudget) btnEditBudget.addEventListener('click', openBudgetModal);
const budgetModalClose = $('#budget-modal-close');
if (budgetModalClose) budgetModalClose.addEventListener('click', closeBudgetModal);
const btnCancelBudget = $('#btn-cancel-budget');
if (btnCancelBudget) btnCancelBudget.addEventListener('click', closeBudgetModal);
const budgetModalOverlay = $('#budget-modal-overlay');
if (budgetModalOverlay) {
  budgetModalOverlay.addEventListener('click', e => {
    if (e.target === e.currentTarget) closeBudgetModal();
  });
}

const budgetForm = $('#budget-form');
if (budgetForm) {
  budgetForm.addEventListener('submit', async e => {
    e.preventDefault();
    const val = parseFloat($('#budget-input-amount').value);
    if (!val || val <= 0) {
      showToast('Please enter a valid budget amount', 'error');
      return;
    }
    await setMonthlyBudget(val);
    closeBudgetModal();
    showToast(`Monthly budget updated to ${formatCurrency(val)}`, 'success');
    loadDashboard();
  });
}

// ── PDF Export Modal ───────────────────────────────────────────
const pdfModalOverlay = $('#pdf-modal-overlay');
const btnExportPdf = $('#btn-export-pdf');

function openPdfModal() {
  if (!pdfModalOverlay) return;
  const yearSelect = $('#pdf-select-year');
  const monthSelect = $('#pdf-select-month');
  const now = new Date();
  const currentYear = now.getFullYear();

  if (yearSelect && yearSelect.children.length === 0) {
    for (let y = currentYear; y >= currentYear - 3; y--) {
      const opt = document.createElement('option');
      opt.value = y;
      opt.textContent = y;
      yearSelect.appendChild(opt);
    }
  }

  if (monthSelect) monthSelect.value = String(now.getMonth() + 1);
  if (yearSelect) yearSelect.value = String(currentYear);

  pdfModalOverlay.classList.add('active');
}

function closePdfModal() {
  if (pdfModalOverlay) pdfModalOverlay.classList.remove('active');
}

if (btnExportPdf) btnExportPdf.addEventListener('click', openPdfModal);
const btnPacingPdf = $('#btn-pacing-pdf-export');
if (btnPacingPdf) btnPacingPdf.addEventListener('click', openPdfModal);
const pdfModalClose = $('#pdf-modal-close');
if (pdfModalClose) pdfModalClose.addEventListener('click', closePdfModal);
const btnCancelPdf = $('#btn-cancel-pdf');
if (btnCancelPdf) btnCancelPdf.addEventListener('click', closePdfModal);
if (pdfModalOverlay) {
  pdfModalOverlay.addEventListener('click', e => {
    if (e.target === e.currentTarget) closePdfModal();
  });
}

const btnConfirmDownloadPdf = $('#btn-confirm-download-pdf');
if (btnConfirmDownloadPdf) {
  btnConfirmDownloadPdf.addEventListener('click', () => {
    const month = $('#pdf-select-month').value;
    const year = $('#pdf-select-year').value;
    window.location.href = `${API}/report/${year}/${month}`;
    closePdfModal();
    showToast(`Downloading PDF report for ${month}/${year}...`, 'info');
  });
}

// Export CSV directly
const btnExport = $('#btn-export');
if (btnExport) {
  btnExport.addEventListener('click', () => {
    window.location.href = `${API}/export`;
    showToast('Downloading CSV export...', 'info');
  });
}

// ── Keyboard Shortcuts Modal ───────────────────────────────────
function openShortcutsModal() {
  const overlay = $('#shortcuts-modal-overlay');
  if (overlay) overlay.classList.add('active');
}

function closeShortcutsModal() {
  const overlay = $('#shortcuts-modal-overlay');
  if (overlay) overlay.classList.remove('active');
}
window.openShortcutsModal = openShortcutsModal;
window.closeShortcutsModal = closeShortcutsModal;

const shortcutsModalClose = $('#shortcuts-modal-close');
if (shortcutsModalClose) shortcutsModalClose.addEventListener('click', closeShortcutsModal);
const shortcutsModalOverlay = $('#shortcuts-modal-overlay');
if (shortcutsModalOverlay) {
  shortcutsModalOverlay.addEventListener('click', e => {
    if (e.target === e.currentTarget) closeShortcutsModal();
  });
}

// ── Global Keyboard Shortcuts ──────────────────────────────────
document.addEventListener('keydown', e => {
  const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
  const isInputActive = activeTag === 'input' || activeTag === 'textarea' || activeTag === 'select';

  // Escape closes all open modals
  if (e.key === 'Escape') {
    closeModal();
    closeDeleteModal();
    closeBudgetModal();
    closePdfModal();
    closeShortcutsModal();
    closeMobileSidebar();
    return;
  }

  // If typing in an input, don't trigger single key hotkeys
  if (isInputActive) return;

  if (e.key === 'n' || e.key === 'N' || e.key === '+') {
    e.preventDefault();
    openModal();
  } else if (e.key === '/') {
    e.preventDefault();
    switchView('expenses');
    setTimeout(() => {
      const searchBox = $('#search-input');
      if (searchBox) searchBox.focus();
    }, 100);
  } else if (e.key === 'd' || e.key === 'D') {
    e.preventDefault();
    switchView('dashboard');
  } else if (e.key === 'e' || e.key === 'E') {
    e.preventDefault();
    switchView('expenses');
  } else if (e.key === '?' || (e.shiftKey && e.key === '/')) {
    e.preventDefault();
    openShortcutsModal();
  } else if (e.key === 't' || e.key === 'T') {
    e.preventDefault();
    toggleTheme();
  }
});

// ── App Init ───────────────────────────────────────────────────
function initApp() {
  initTheme();
  loadDashboard();

  // Check for login success or other pending notifications from previous page
  const pendingToast = sessionStorage.getItem('pendingToast');
  if (pendingToast) {
    sessionStorage.removeItem('pendingToast');
    try {
      const parsed = JSON.parse(pendingToast);
      showToast(parsed.message, parsed.type || 'success');
    } catch (e) {
      showToast(pendingToast, 'success');
    }
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}
