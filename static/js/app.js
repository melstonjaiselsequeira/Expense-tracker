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

function debounce(fn, delay = 300) {
  let timer = null;
  return function(...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

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
         'light';
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
  const theme = saved || 'light';
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

  // Show global header on Dashboard only; hide on all other views
  const globalHeader = $('#global-top-header') || $('.top-nav-bar');
  if (globalHeader) {
    globalHeader.style.display = (viewName === 'dashboard') ? '' : 'none';
  }
  if (document.body) {
    document.body.setAttribute('data-active-view', viewName);
  }

  window.scrollTo({ top: 0, behavior: 'instant' });
  closeMobileSidebar();

  if (viewName === 'dashboard') {
    loadDashboard();
  } else if (viewName === 'expenses') {
    loadExpenses();
  } else if (viewName === 'reports') {
    populateReportYears();
    loadReportHistory();
  } else if (viewName === 'support') {
    loadSupportTickets();
    loadQuickQuestions();
    loadFAQs();
  } else if (viewName === 'admin-support' || viewName === 'admin-dashboard') {
    loadAdminDashboard();
  } else if (viewName === 'admin-all-tickets') {
    loadAdminAllTickets();
  } else if (viewName === 'admin-queries') {
    loadAdminGeneralQueries();
  } else if (viewName === 'admin-problems') {
    loadAdminReportedProblems();
  } else if (viewName === 'admin-features') {
    loadAdminFeatureRequests();
  } else if (viewName === 'admin-conversations') {
    loadAdminConversations();
  } else if (viewName === 'admin-faq') {
    loadAdminFAQs();
  } else if (viewName === 'admin-user-history') {
    loadAdminUserHistorySection();
  }

  // Sync active states on top admin tabs if on an admin view
  if (viewName.startsWith('admin-')) {
    $$('.admin-tabs-nav .admin-tab-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.adminView === viewName);
    });
    updateAdminBadges();
  }

  // Keep URL query parameter in sync with the active view
  try {
    const currentUrl = new URL(window.location.href);
    if (viewName === 'dashboard') {
      currentUrl.searchParams.delete('view');
    } else {
      currentUrl.searchParams.set('view', viewName);
    }
    window.history.replaceState({}, '', currentUrl.toString());
  } catch (e) {}
}

$$('.nav-item').forEach(item => {
  item.addEventListener('click', e => {
    e.preventDefault();
    if (item.id === 'btn-download-reports') {
      switchView('reports');
      closeMobileSidebar();
      return;
    }
    if (item.dataset.view) {
      switchView(item.dataset.view);
    }
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

// ── Download Reports System & History ─────────────────────────
let currentReportPeriod = 'monthly';
let currentReportFormat = 'pdf';

function populateReportYears() {
  const monthYearSelect = $('#report-select-year-month');
  const yearlySelect = $('#report-select-year');
  const now = new Date();
  const currentYear = now.getFullYear();

  [monthYearSelect, yearlySelect].forEach(sel => {
    if (sel && sel.children.length === 0) {
      // Allow historical years down to 10 years in the past
      for (let y = currentYear; y >= currentYear - 10; y--) {
        const opt = document.createElement('option');
        opt.value = y;
        opt.textContent = y;
        sel.appendChild(opt);
      }
    }
  });

  if (monthYearSelect) monthYearSelect.value = String(currentYear);
  if (yearlySelect) yearlySelect.value = String(currentYear);
  const monthSelect = $('#report-select-month');
  if (monthSelect) monthSelect.value = String(now.getMonth() + 1);

  // Set default dates for custom range
  const startDateInput = $('#report-start-date');
  const endDateInput = $('#report-end-date');
  if (startDateInput && !startDateInput.value) {
    const firstDay = new Date(currentYear, now.getMonth(), 1);
    startDateInput.value = firstDay.toISOString().split('T')[0];
  }
  if (endDateInput && !endDateInput.value) {
    endDateInput.value = now.toISOString().split('T')[0];
  }
}

function switchReportPeriod(period) {
  currentReportPeriod = period;
  $$('#report-period-pills .period-pill').forEach(pill => {
    pill.classList.toggle('active', pill.dataset.period === period);
  });

  const monthlyCtrl = $('#controls-monthly');
  const yearlyCtrl = $('#controls-yearly');
  const customCtrl = $('#controls-custom');

  if (monthlyCtrl) monthlyCtrl.style.display = (period === 'monthly') ? 'block' : 'none';
  if (yearlyCtrl) yearlyCtrl.style.display = (period === 'yearly') ? 'block' : 'none';
  if (customCtrl) customCtrl.style.display = (period === 'custom') ? 'block' : 'none';
}

function switchReportFormat(format) {
  currentReportFormat = format;
  $$('#report-format-grid .format-card').forEach(card => {
    card.classList.toggle('active', card.dataset.format === format);
  });
}

// Instant Statement Export on Dashboard (Current Month PDF)
const btnPacingPdf = $('#btn-pacing-pdf-export');
if (btnPacingPdf) {
  btnPacingPdf.addEventListener('click', () => {
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth() + 1;
    showToast(`Downloading current month PDF report (${month}/${year})...`, 'info');
    window.location.href = `${API}/report/${year}/${month}`;
  });
}

// Legacy export buttons support if present
const btnExportPdf = $('#btn-export-pdf');
if (btnExportPdf) {
  btnExportPdf.addEventListener('click', () => {
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth() + 1;
    window.location.href = `${API}/report/${year}/${month}`;
  });
}

const btnExport = $('#btn-export');
if (btnExport) {
  btnExport.addEventListener('click', () => {
    window.location.href = `${API}/export`;
    showToast('Downloading CSV export...', 'info');
  });
}

// Period Pill Clicks
$$('#report-period-pills .period-pill').forEach(pill => {
  pill.addEventListener('click', () => {
    switchReportPeriod(pill.dataset.period);
  });
});

// Format Card Clicks
$$('#report-format-grid .format-card').forEach(card => {
  card.addEventListener('click', () => {
    switchReportFormat(card.dataset.format);
  });
});

// Download Action Execution
const btnConfirmDownloadReport = $('#btn-confirm-download-report');
if (btnConfirmDownloadReport) {
  btnConfirmDownloadReport.addEventListener('click', async () => {
    const params = new URLSearchParams();
    params.append('period_type', currentReportPeriod);
    params.append('format', currentReportFormat);

    let periodDesc = '';
    if (currentReportPeriod === 'monthly') {
      const month = $('#report-select-month') ? $('#report-select-month').value : '1';
      const year = $('#report-select-year-month') ? $('#report-select-year-month').value : new Date().getFullYear();
      params.append('month', month);
      params.append('year', year);
      periodDesc = `${month}/${year}`;
    } else if (currentReportPeriod === 'yearly') {
      const year = $('#report-select-year') ? $('#report-select-year').value : new Date().getFullYear();
      params.append('year', year);
      periodDesc = `Year ${year}`;
    } else if (currentReportPeriod === 'custom') {
      const startDate = $('#report-start-date') ? $('#report-start-date').value : '';
      const endDate = $('#report-end-date') ? $('#report-end-date').value : '';
      if (!startDate || !endDate) {
        showToast('Please select both start and end dates', 'error');
        return;
      }
      if (startDate > endDate) {
        showToast('Start date cannot be after end date', 'error');
        return;
      }
      params.append('start_date', startDate);
      params.append('end_date', endDate);
      periodDesc = `${startDate} to ${endDate}`;
    }

    const downloadBtnText = $('#btn-download-report-text');
    const originalText = downloadBtnText ? downloadBtnText.textContent : 'Generate & Download Report';
    btnConfirmDownloadReport.disabled = true;
    if (downloadBtnText) downloadBtnText.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating...';

    try {
      showToast(`Generating ${currentReportFormat.toUpperCase()} report for ${periodDesc}...`, 'info');
      const resp = await fetch(`${API}/reports/download?${params.toString()}`);
      
      if (!resp.ok) {
        let errMsg = 'Failed to generate report';
        try {
          const errData = await resp.json();
          errMsg = errData.error || errMsg;
        } catch (_) {}
        showToast(errMsg, resp.status === 404 ? 'warning' : 'error');
        return;
      }

      // Extract filename from header or build sensible default
      let filename = `ExpenseFlow_Report.${currentReportFormat}`;
      const disposition = resp.headers.get('Content-Disposition') || resp.headers.get('content-disposition');
      if (disposition && disposition.includes('filename=')) {
        const matches = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(disposition);
        if (matches != null && matches[1]) {
          filename = matches[1].replace(/['"]/g, '').trim();
        }
      }

      const blob = await resp.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(blobUrl);

      showToast(`Report downloaded successfully: ${filename}`, 'success');
      loadReportHistory();

    } catch (err) {
      console.error('Error downloading report:', err);
      showToast('Network error while downloading report. Please try again.', 'error');
    } finally {
      btnConfirmDownloadReport.disabled = false;
      if (downloadBtnText) downloadBtnText.textContent = originalText;
    }
  });
}

// ── Report History Management ──────────────────────────────────
async function loadReportHistory() {
  const tbody = $('#report-history-tbody');
  const table = $('#report-history-table');
  const emptyState = $('#reports-empty-state');
  if (!tbody) return;

  try {
    const resp = await fetch(`${API}/reports/history`);
    if (!resp.ok) {
      console.warn('Failed to fetch report history:', resp.status);
      return;
    }
    const data = await resp.json();
    const history = data.history || [];

    if (history.length === 0) {
      if (table && table.parentElement) table.parentElement.style.display = 'none';
      if (emptyState) emptyState.style.display = 'block';
      tbody.innerHTML = '';
      return;
    }

    if (table && table.parentElement) table.parentElement.style.display = 'block';
    if (emptyState) emptyState.style.display = 'none';

    tbody.innerHTML = history.map(item => {
      const formatLower = (item.format || 'pdf').toLowerCase();
      let formatIcon = 'fa-file-pdf';
      if (formatLower === 'csv') formatIcon = 'fa-file-csv';
      if (formatLower === 'xlsx') formatIcon = 'fa-file-excel';

      const dateRangeText = (item.start_date === item.end_date)
        ? formatDate(item.start_date)
        : `${formatDate(item.start_date)} – ${formatDate(item.end_date)}`;

      return `
        <tr>
          <td><strong>${escapeHtml(item.report_name)}</strong></td>
          <td><span class="badge" style="background: rgba(255, 255, 255, 0.05);">${escapeHtml(item.report_type)}</span></td>
          <td style="color: var(--text-secondary); font-size: 0.85rem;">${dateRangeText}</td>
          <td>
            <span class="report-format-badge ${formatLower}">
              <i class="fas ${formatIcon}"></i> ${escapeHtml(item.format)}
            </span>
          </td>
          <td style="color: var(--text-secondary); font-size: 0.85rem;">${formatDateTime(item.created_at)}</td>
          <td style="text-align: right;">
            <button type="button" class="btn-download-again" data-report-id="${item.id}" title="Download this report again">
              <i class="fas fa-download"></i> <span>Download Again</span>
            </button>
          </td>
        </tr>
      `;
    }).join('');

    tbody.querySelectorAll('.btn-download-again').forEach(btn => {
      btn.addEventListener('click', () => {
        const reportId = btn.dataset.reportId;
        if (reportId) downloadReportAgain(reportId, btn);
      });
    });

  } catch (err) {
    console.error('Error loading report history:', err);
  }
}

async function downloadReportAgain(reportId, btnElement) {
  const originalHtml = btnElement ? btnElement.innerHTML : '';
  if (btnElement) {
    btnElement.disabled = true;
    btnElement.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Downloading...';
  }

  try {
    showToast('Regenerating report from history...', 'info');
    const resp = await fetch(`${API}/reports/download-again/${reportId}`);

    if (!resp.ok) {
      let errMsg = 'Failed to download report';
      try {
        const errData = await resp.json();
        errMsg = errData.error || errMsg;
      } catch (_) {}
      showToast(errMsg, resp.status === 404 ? 'warning' : 'error');
      return;
    }

    let filename = `ExpenseFlow_Report`;
    const disposition = resp.headers.get('Content-Disposition') || resp.headers.get('content-disposition');
    if (disposition && disposition.includes('filename=')) {
      const matches = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(disposition);
      if (matches != null && matches[1]) {
        filename = matches[1].replace(/['"]/g, '').trim();
      }
    }

    const blob = await resp.blob();
    const blobUrl = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(blobUrl);

    showToast(`Report downloaded successfully: ${filename}`, 'success');
  } catch (err) {
    console.error('Error downloading report again:', err);
    showToast('Network error while regenerating report. Please try again.', 'error');
  } finally {
    if (btnElement) {
      btnElement.disabled = false;
      btnElement.innerHTML = originalHtml;
    }
  }
}

const btnRefreshReportHistory = $('#btn-refresh-report-history');
if (btnRefreshReportHistory) {
  btnRefreshReportHistory.addEventListener('click', () => {
    btnRefreshReportHistory.disabled = true;
    const orig = btnRefreshReportHistory.innerHTML;
    btnRefreshReportHistory.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Refreshing...';
    loadReportHistory().finally(() => {
      btnRefreshReportHistory.disabled = false;
      btnRefreshReportHistory.innerHTML = orig;
    });
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

// ── Help & Support System ──────────────────────────────────────
let activeTicketAttachment = null;
let currentViewingTicketId = null;
let adminSearchDebounceTimer = null;

function formatDateTime(isoStr) {
  if (!isoStr) return '-';
  try {
    const d = new Date(isoStr);
    return d.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  } catch (e) {
    return isoStr;
  }
}

function getCategoryBadgeHtml(cat) {
  let badgeClass = 'general';
  let icon = 'fa-circle-question';
  if (cat === 'Report a Problem') {
    badgeClass = 'problem';
    icon = 'fa-bug';
  } else if (cat === 'Feature Request') {
    badgeClass = 'feature';
    icon = 'fa-lightbulb';
  }
  return `<span class="ticket-category-badge ${badgeClass}"><i class="fas ${icon}"></i> ${escapeHtml(cat || 'General')}</span>`;
}

function getStatusBadgeHtml(status) {
  let badgeClass = 'open';
  let icon = 'fa-clock';
  const s = (status || '').toLowerCase();
  if (s === 'in progress') {
    badgeClass = 'in-progress';
    icon = 'fa-spinner fa-spin-pulse';
  } else if (s === 'resolved') {
    badgeClass = 'resolved';
    icon = 'fa-circle-check';
  } else if (s === 'closed') {
    badgeClass = 'closed';
    icon = 'fa-circle-xmark';
  } else if (s === 'rejected') {
    badgeClass = 'rejected';
    icon = 'fa-ban';
  } else if (s === 'pending') {
    badgeClass = 'pending';
    icon = 'fa-hourglass-half';
  }
  return `<span class="ticket-status-badge ${badgeClass}"><i class="fas ${icon}"></i> ${escapeHtml(status || 'Open')}</span>`;
}

async function loadSupportTickets() {
  const tbody = $('#support-tickets-tbody');
  const emptyState = $('#support-empty-state');
  const table = $('#support-tickets-table');
  const userBadge = $('#user-tickets-badge');
  const userCount = $('#user-tickets-count');
  if (!tbody) return;

  try {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 2rem; color: var(--text-muted);"><i class="fas fa-spinner fa-spin"></i> Loading tickets...</td></tr>`;
    const resp = await fetch('/api/support/tickets');
    if (!resp.ok) throw new Error('Failed to load support tickets');
    const data = await resp.json();
    const tickets = data.tickets || [];

    if (userBadge) userBadge.textContent = tickets.length;
    if (userCount) userCount.textContent = tickets.length;

    if (tickets.length === 0) {
      if (table) table.style.display = 'none';
      if (emptyState) emptyState.style.display = 'block';
      tbody.innerHTML = '';
      return;
    }

    if (table) table.style.display = 'table';
    if (emptyState) emptyState.style.display = 'none';

    tbody.innerHTML = tickets.map(t => `
      <tr>
        <td style="font-weight: 700; color: var(--accent);"><i class="fas fa-ticket" style="margin-right: 4px; font-size: 0.8rem;"></i>${escapeHtml(t.ticket_id)}</td>
        <td style="font-weight: 600; color: var(--text-primary); max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(t.subject)}</td>
        <td>${getCategoryBadgeHtml(t.category)}</td>
        <td style="color: var(--text-secondary); font-size: 0.85rem;">${formatDateTime(t.created_at)}</td>
        <td style="color: var(--text-secondary); font-size: 0.85rem;">${formatDateTime(t.updated_at)}</td>
        <td>${getStatusBadgeHtml(t.status)}</td>
        <td style="text-align: right;">
          <button type="button" class="btn-icon edit btn-view-ticket" data-ticket-id="${t.id}" title="View Ticket Details">
            <i class="fas fa-eye"></i>
          </button>
        </td>
      </tr>
    `).join('');

    // Attach click listeners to view buttons
    tbody.querySelectorAll('.btn-view-ticket').forEach(btn => {
      btn.addEventListener('click', () => {
        openTicketDetailsModal(btn.dataset.ticketId);
      });
    });

  } catch (err) {
    console.error('Error loading support tickets:', err);
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 2rem; color: var(--danger);"><i class="fas fa-exclamation-circle"></i> Failed to load tickets. Please try again.</td></tr>`;
  }
}

async function openTicketDetailsModal(ticketId) {
  const modalOverlay = $('#ticket-modal-overlay');
  if (!modalOverlay) return;

  currentViewingTicketId = ticketId;

  try {
    const resp = await fetch(`/api/support/tickets/${ticketId}`);
    if (!resp.ok) {
      showToast('Could not load ticket details', 'error');
      return;
    }
    const data = await resp.json();
    const t = data.ticket;

    $('#modal-ticket-id').textContent = t.ticket_id;
    $('#ticket-detail-user').textContent = t.user_name ? `${t.user_name} (${t.user_email})` : 'You';
    $('#ticket-detail-category').innerHTML = getCategoryBadgeHtml(t.category);
    $('#ticket-detail-status').innerHTML = getStatusBadgeHtml(t.status);
    $('#ticket-detail-date').textContent = formatDateTime(t.created_at);
    $('#ticket-detail-subject').textContent = t.subject;
    $('#ticket-detail-description').textContent = t.description;

    // Screenshot attachment
    const attachmentSec = $('#ticket-attachment-section');
    if (t.has_attachment && t.attachment_filename) {
      attachmentSec.style.display = 'block';
      const fileUrl = `/api/support/attachments/${encodeURIComponent(t.attachment_filename)}`;
      $('#ticket-attachment-img').src = fileUrl;
      $('#ticket-attachment-link').href = fileUrl;
    } else {
      attachmentSec.style.display = 'none';
    }

    // User Response / Support Team Reply View
    const userNotesSec = $('#ticket-user-notes-section');
    const userPendingSec = $('#ticket-user-pending-section');
    if (t.admin_notes && t.admin_notes.trim()) {
      if (userNotesSec) {
        userNotesSec.style.display = 'block';
        $('#ticket-user-notes-text').textContent = t.admin_notes;
      }
      if (userPendingSec) userPendingSec.style.display = 'none';
    } else {
      if (userNotesSec) userNotesSec.style.display = 'none';
      if (userPendingSec) userPendingSec.style.display = 'block';
    }

    // Admin Controls
    const adminStatusSelect = $('#admin-update-status');
    const adminNotesTextarea = $('#admin-update-notes');
    if (adminStatusSelect) {
      adminStatusSelect.value = t.status || 'Open';
    }
    if (adminNotesTextarea) {
      adminNotesTextarea.value = t.admin_notes || '';
    }

    modalOverlay.classList.add('active');
  } catch (err) {
    console.error('Error fetching ticket detail:', err);
    showToast('Failed to load ticket details', 'error');
  }
}

function closeTicketDetailsModal() {
  const modalOverlay = $('#ticket-modal-overlay');
  if (modalOverlay) modalOverlay.classList.remove('active');
  currentViewingTicketId = null;
}

// ══════════════════════════════════════════════════════════════════
// ADMIN SUPPORT MANAGEMENT SUITE — CONTROLLERS & DATA HANDLERS
// ══════════════════════════════════════════════════════════════════

let currentAdminActiveTicketId = null;
let adminAllTicketsCache = [];
let adminUsersCache = [];

// ── Shared Helper: Format Date Time ──
function formatDateTime(isoStr) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  if (isNaN(d.getTime())) return isoStr;
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  }) + ' ' + d.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit'
  });
}

// ── 1. Update All Admin Badges & KPI Counters ──
async function updateAdminBadges() {
  try {
    const res = await fetch('/api/admin/support/dashboard');
    if (!res.ok) return;
    const data = await res.json();
    const stats = data.stats || {};
    const recentTickets = data.recent_tickets || [];

    // Dashboard Stat Cards
    const totalEl = $('#dash-total-tickets');
    const openEl = $('#dash-open-tickets');
    const inprogressEl = $('#dash-inprogress-tickets');
    const resolvedEl = $('#dash-resolved-tickets');

    if (totalEl) totalEl.textContent = stats.total_tickets || 0;
    if (openEl) openEl.textContent = stats.open_tickets || 0;
    if (inprogressEl) inprogressEl.textContent = stats.in_progress_tickets || 0;
    if (resolvedEl) resolvedEl.textContent = stats.resolved_tickets || 0;

    // Sidebar & Top Nav Pill Badges
    const allTotal = stats.total_tickets || 0;
    const queriesTotal = (stats.by_category && stats.by_category.general_query) || 0;
    const problemsTotal = (stats.by_category && stats.by_category.report_problem) || 0;
    const featuresTotal = (stats.by_category && stats.by_category.feature_request) || 0;

    $$('.admin-pill-all, #sidebar-badge-all').forEach(el => el.textContent = allTotal);
    $$('.admin-pill-queries, #sidebar-badge-queries').forEach(el => el.textContent = queriesTotal);
    $$('.admin-pill-problems, #sidebar-badge-problems').forEach(el => el.textContent = problemsTotal);
    $$('.admin-pill-features, #sidebar-badge-features').forEach(el => el.textContent = featuresTotal);

    // Category Distribution Bars
    const catQueryCountEl = $('#dash-cat-query-count');
    const catProbCountEl = $('#dash-cat-prob-count');
    const catFeatCountEl = $('#dash-cat-feat-count');

    const catQueryBar = $('#dash-cat-query-bar');
    const catProbBar = $('#dash-cat-prob-bar');
    const catFeatBar = $('#dash-cat-feat-bar');

    const queryPct = allTotal > 0 ? Math.round((queriesTotal / allTotal) * 100) : 0;
    const probPct = allTotal > 0 ? Math.round((problemsTotal / allTotal) * 100) : 0;
    const featPct = allTotal > 0 ? Math.round((featuresTotal / allTotal) * 100) : 0;

    if (catQueryCountEl) catQueryCountEl.textContent = `${queriesTotal} (${queryPct}%)`;
    if (catProbCountEl) catProbCountEl.textContent = `${problemsTotal} (${probPct}%)`;
    if (catFeatCountEl) catFeatCountEl.textContent = `${featuresTotal} (${featPct}%)`;

    if (catQueryBar) catQueryBar.style.width = `${queryPct}%`;
    if (catProbBar) catProbBar.style.width = `${probPct}%`;
    if (catFeatBar) catFeatBar.style.width = `${featPct}%`;

    // Render Recent Tickets Table on Dashboard
    const recentTbody = $('#admin-recent-tickets-tbody');
    if (recentTbody) {
      if (recentTickets.length === 0) {
        recentTbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 2rem; color: var(--text-muted);">No support tickets submitted yet.</td></tr>`;
      } else {
        recentTbody.innerHTML = recentTickets.map(t => `
          <tr>
            <td style="font-weight: 700; color: var(--accent);"><i class="fas fa-ticket" style="margin-right: 4px; font-size: 0.8rem;"></i>${escapeHtml(t.ticket_id)}</td>
            <td>
              <div style="font-weight: 600; color: var(--text-primary); font-size: 0.88rem;">${escapeHtml(t.user_name || 'Customer')}</div>
              <div style="font-size: 0.76rem; color: var(--text-muted);">${escapeHtml(t.user_email || '')}</div>
            </td>
            <td>${getCategoryBadgeHtml(t.category)}</td>
            <td style="font-weight: 600; color: var(--text-primary); max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(t.subject)}</td>
            <td style="color: var(--text-secondary); font-size: 0.85rem;">${formatDateTime(t.created_at)}</td>
            <td>${getStatusBadgeHtml(t.status)}</td>
            <td style="text-align: right;">
              <button type="button" class="btn-table-action" onclick="openAdminConversation(${t.id})" title="Open Conversation Thread">
                <i class="fas fa-comments" style="color: var(--accent);"></i>
              </button>
            </td>
          </tr>
        `).join('');
      }
    }

  } catch (err) {
    console.error('Error updating admin badges:', err);
  }
}

// ── 2. Support Dashboard View ──
async function loadAdminDashboard() {
  await updateAdminBadges();
}

// ── 3. All Support Tickets View ──
async function loadAdminAllTickets() {
  const tbody = $('#admin-all-tbody');
  const emptyState = $('#admin-all-empty');
  const table = $('#admin-all-table');
  const countEl = $('#admin-all-count');
  if (!tbody) return;

  const status = $('#admin-all-filter-status') ? $('#admin-all-filter-status').value : 'All';
  const category = $('#admin-all-filter-category') ? $('#admin-all-filter-category').value : 'All';
  const sort = $('#admin-all-sort') ? $('#admin-all-sort').value : 'date_desc';
  const search = $('#admin-all-search') ? $('#admin-all-search').value.trim() : '';

  try {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 2rem; color: var(--text-muted);"><i class="fas fa-spinner fa-spin"></i> Loading tickets...</td></tr>`;

    const params = new URLSearchParams();
    if (status && status !== 'All') params.append('status', status);
    if (category && category !== 'All') params.append('category', category);
    if (sort) params.append('sort', sort);
    if (search) params.append('search', search);

    const resp = await fetch(`/api/admin/support/tickets?${params.toString()}`);
    if (!resp.ok) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 2rem; color: var(--danger);"><i class="fas fa-ban"></i> Admin authorization required.</td></tr>`;
      return;
    }

    const data = await resp.json();
    adminAllTicketsCache = data.tickets || [];
    if (countEl) countEl.textContent = adminAllTicketsCache.length;
    $$('.admin-pill-all, #sidebar-badge-all').forEach(el => el.textContent = adminAllTicketsCache.length);

    if (adminAllTicketsCache.length === 0) {
      if (table) table.style.display = 'none';
      if (emptyState) emptyState.style.display = 'block';
      tbody.innerHTML = '';
      return;
    }

    if (table) table.style.display = 'table';
    if (emptyState) emptyState.style.display = 'none';

    tbody.innerHTML = adminAllTicketsCache.map(t => `
      <tr>
        <td style="font-weight: 700; color: var(--accent);"><i class="fas fa-ticket" style="margin-right: 4px; font-size: 0.8rem;"></i>${escapeHtml(t.ticket_id)}</td>
        <td>
          <div style="font-weight: 600; color: var(--text-primary); font-size: 0.88rem;">${escapeHtml(t.user_name || 'Customer')}</div>
          <div style="font-size: 0.76rem; color: var(--text-muted);">${escapeHtml(t.user_email || '')}</div>
        </td>
        <td>${getCategoryBadgeHtml(t.category)}</td>
        <td style="font-weight: 600; color: var(--text-primary); max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(t.subject)}</td>
        <td style="color: var(--text-secondary); font-size: 0.85rem;">${formatDateTime(t.created_at)}</td>
        <td>${getStatusBadgeHtml(t.status)}</td>
        <td style="text-align: right; white-space: nowrap;">
          <button type="button" class="btn-table-action" onclick="openAdminConversation(${t.id})" title="Open Conversation Thread">
            <i class="fas fa-comments" style="color: var(--accent);"></i>
          </button>
          <button type="button" class="btn-table-action" onclick="openTicketDetailsModal(${t.id})" title="Quick Manage Status & Notes">
            <i class="fas fa-sliders"></i>
          </button>
        </td>
      </tr>
    `).join('');

  } catch (err) {
    console.error('Error loading all tickets:', err);
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 2rem; color: var(--danger);"><i class="fas fa-exclamation-circle"></i> Error loading tickets.</td></tr>`;
  }
}

// ── 4. General Queries View ──
async function loadAdminGeneralQueries() {
  const tbody = $('#admin-queries-tbody');
  const emptyState = $('#admin-queries-empty');
  const table = $('#admin-queries-table');
  const countEl = $('#admin-queries-count');
  if (!tbody) return;

  const status = $('#admin-queries-filter-status') ? $('#admin-queries-filter-status').value : 'All';
  const search = $('#admin-queries-search') ? $('#admin-queries-search').value.trim() : '';

  try {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 2rem; color: var(--text-muted);"><i class="fas fa-spinner fa-spin"></i> Loading general queries...</td></tr>`;

    const params = new URLSearchParams();
    params.append('category', 'General Query');
    if (status && status !== 'All') params.append('status', status);
    if (search) params.append('search', search);

    const resp = await fetch(`/api/admin/support/tickets?${params.toString()}`);
    if (!resp.ok) throw new Error('Failed to load general queries');

    const data = await resp.json();
    const tickets = data.tickets || [];
    if (countEl) countEl.textContent = tickets.length;
    $$('.admin-pill-queries, #sidebar-badge-queries').forEach(el => el.textContent = tickets.length);

    if (tickets.length === 0) {
      if (table) table.style.display = 'none';
      if (emptyState) emptyState.style.display = 'block';
      tbody.innerHTML = '';
      return;
    }

    if (table) table.style.display = 'table';
    if (emptyState) emptyState.style.display = 'none';

    tbody.innerHTML = tickets.map(t => `
      <tr>
        <td style="font-weight: 700; color: var(--accent);"><i class="fas fa-ticket" style="margin-right: 4px; font-size: 0.8rem;"></i>${escapeHtml(t.ticket_id)}</td>
        <td>
          <div style="font-weight: 600; color: var(--text-primary); font-size: 0.88rem;">${escapeHtml(t.user_name || 'Customer')}</div>
          <div style="font-size: 0.76rem; color: var(--text-muted);">${escapeHtml(t.user_email || '')}</div>
        </td>
        <td style="font-weight: 600; color: var(--text-primary); max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(t.subject)}</td>
        <td style="color: var(--text-secondary); font-size: 0.85rem;">${formatDateTime(t.created_at)}</td>
        <td>${getStatusBadgeHtml(t.status)}</td>
        <td style="text-align: right;">
          <button type="button" class="btn-table-action" onclick="openAdminConversation(${t.id})" title="Open & Respond">
            <i class="fas fa-reply" style="color: var(--accent);"></i>
          </button>
        </td>
      </tr>
    `).join('');

  } catch (err) {
    console.error('Error loading general queries:', err);
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 2rem; color: var(--danger);"><i class="fas fa-exclamation-circle"></i> Error loading general queries.</td></tr>`;
  }
}

// ── 5. Reported Problems View ──
async function loadAdminReportedProblems() {
  const tbody = $('#admin-problems-tbody');
  const emptyState = $('#admin-problems-empty');
  const table = $('#admin-problems-table');
  const countEl = $('#admin-problems-count');
  if (!tbody) return;

  const status = $('#admin-problems-filter-status') ? $('#admin-problems-filter-status').value : 'All';
  const attachFilter = $('#admin-problems-filter-attachment') ? $('#admin-problems-filter-attachment').value : 'All';
  const search = $('#admin-problems-search') ? $('#admin-problems-search').value.trim() : '';

  try {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 2rem; color: var(--text-muted);"><i class="fas fa-spinner fa-spin"></i> Loading reported problems...</td></tr>`;

    const params = new URLSearchParams();
    params.append('category', 'Report a Problem');
    if (status && status !== 'All') params.append('status', status);
    if (search) params.append('search', search);

    const resp = await fetch(`/api/admin/support/tickets?${params.toString()}`);
    if (!resp.ok) throw new Error('Failed to load reported problems');

    const data = await resp.json();
    let tickets = data.tickets || [];

    if (attachFilter === 'with_attachment') {
      tickets = tickets.filter(t => t.has_attachment);
    }

    if (countEl) countEl.textContent = tickets.length;
    $$('.admin-pill-problems, #sidebar-badge-problems').forEach(el => el.textContent = tickets.length);

    if (tickets.length === 0) {
      if (table) table.style.display = 'none';
      if (emptyState) emptyState.style.display = 'block';
      tbody.innerHTML = '';
      return;
    }

    if (table) table.style.display = 'table';
    if (emptyState) emptyState.style.display = 'none';

    tbody.innerHTML = tickets.map(t => {
      const attachBadge = t.has_attachment
        ? `<a href="/api/support/attachments/${encodeURIComponent(t.attachment_filename)}" target="_blank" class="admin-badge badge-active" title="View attached screenshot"><i class="fas fa-paperclip"></i> Screenshot</a>`
        : `<span style="font-size: 0.8rem; color: var(--text-muted);">None</span>`;

      return `
        <tr>
          <td style="font-weight: 700; color: var(--accent);"><i class="fas fa-ticket" style="margin-right: 4px; font-size: 0.8rem;"></i>${escapeHtml(t.ticket_id)}</td>
          <td>
            <div style="font-weight: 600; color: var(--text-primary); font-size: 0.88rem;">${escapeHtml(t.user_name || 'Customer')}</div>
            <div style="font-size: 0.76rem; color: var(--text-muted);">${escapeHtml(t.user_email || '')}</div>
          </td>
          <td style="font-weight: 600; color: var(--text-primary); max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(t.subject)}</td>
          <td>${attachBadge}</td>
          <td style="color: var(--text-secondary); font-size: 0.85rem;">${formatDateTime(t.created_at)}</td>
          <td>${getStatusBadgeHtml(t.status)}</td>
          <td style="text-align: right;">
            <button type="button" class="btn-table-action" onclick="openAdminConversation(${t.id})" title="Investigate & Respond">
              <i class="fas fa-magnifying-glass-chart" style="color: #06b6d4;"></i>
            </button>
          </td>
        </tr>
      `;
    }).join('');

  } catch (err) {
    console.error('Error loading reported problems:', err);
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 2rem; color: var(--danger);"><i class="fas fa-exclamation-circle"></i> Error loading reported problems.</td></tr>`;
  }
}

// ── 6. Feature Requests View ──
async function loadAdminFeatureRequests() {
  const tbody = $('#admin-features-tbody');
  const emptyState = $('#admin-features-empty');
  const table = $('#admin-features-table');
  const countEl = $('#admin-features-count');
  if (!tbody) return;

  const status = $('#admin-features-filter-status') ? $('#admin-features-filter-status').value : 'All';
  const search = $('#admin-features-search') ? $('#admin-features-search').value.trim() : '';

  try {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 2rem; color: var(--text-muted);"><i class="fas fa-spinner fa-spin"></i> Loading feature requests...</td></tr>`;

    const params = new URLSearchParams();
    params.append('category', 'Feature Request');
    if (status && status !== 'All') params.append('status', status);
    if (search) params.append('search', search);

    const resp = await fetch(`/api/admin/support/tickets?${params.toString()}`);
    if (!resp.ok) throw new Error('Failed to load feature requests');

    const data = await resp.json();
    const tickets = data.tickets || [];
    if (countEl) countEl.textContent = tickets.length;
    $$('.admin-pill-features, #sidebar-badge-features').forEach(el => el.textContent = tickets.length);

    if (tickets.length === 0) {
      if (table) table.style.display = 'none';
      if (emptyState) emptyState.style.display = 'block';
      tbody.innerHTML = '';
      return;
    }

    if (table) table.style.display = 'table';
    if (emptyState) emptyState.style.display = 'none';

    tbody.innerHTML = tickets.map(t => `
      <tr>
        <td style="font-weight: 700; color: var(--accent);"><i class="fas fa-ticket" style="margin-right: 4px; font-size: 0.8rem;"></i>${escapeHtml(t.ticket_id)}</td>
        <td>
          <div style="font-weight: 600; color: var(--text-primary); font-size: 0.88rem;">${escapeHtml(t.user_name || 'Customer')}</div>
          <div style="font-size: 0.76rem; color: var(--text-muted);">${escapeHtml(t.user_email || '')}</div>
        </td>
        <td style="font-weight: 600; color: var(--text-primary); max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(t.subject)}</td>
        <td style="color: var(--text-secondary); font-size: 0.85rem;">${formatDateTime(t.created_at)}</td>
        <td>${getStatusBadgeHtml(t.status)}</td>
        <td style="text-align: right;">
          <button type="button" class="btn-table-action" onclick="openAdminConversation(${t.id})" title="Review & Respond">
            <i class="fas fa-lightbulb" style="color: #06b6d4;"></i>
          </button>
        </td>
      </tr>
    `).join('');

  } catch (err) {
    console.error('Error loading feature requests:', err);
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 2rem; color: var(--danger);"><i class="fas fa-exclamation-circle"></i> Error loading feature requests.</td></tr>`;
  }
}

// ── 7. Ticket Conversations Controller ──
let adminQueueTicketsList = [];

async function loadAdminConversations(preselectedTicketId = null) {
  const queueList = $('#admin-convo-queue-list');
  if (!queueList) return;

  try {
    queueList.innerHTML = `<div style="padding: 2rem; text-align: center; color: var(--text-muted);"><i class="fas fa-spinner fa-spin"></i> Loading ticket queue...</div>`;

    const resp = await fetch('/api/admin/support/tickets?sort=date_desc');
    if (!resp.ok) throw new Error('Failed to load tickets queue');
    const data = await resp.json();
    adminQueueTicketsList = data.tickets || [];

    renderAdminConvoQueue();

    if (preselectedTicketId) {
      selectAdminConversation(preselectedTicketId);
    } else if (currentAdminActiveTicketId && adminQueueTicketsList.some(t => t.id === currentAdminActiveTicketId)) {
      selectAdminConversation(currentAdminActiveTicketId);
    } else if (adminQueueTicketsList.length > 0) {
      selectAdminConversation(adminQueueTicketsList[0].id);
    }

  } catch (err) {
    console.error('Error loading conversations queue:', err);
    queueList.innerHTML = `<div style="padding: 2rem; text-align: center; color: var(--danger);"><i class="fas fa-exclamation-circle"></i> Error loading tickets.</div>`;
  }
}

function renderAdminConvoQueue() {
  const queueList = $('#admin-convo-queue-list');
  if (!queueList) return;

  const searchInput = $('#admin-convo-queue-search');
  const searchVal = searchInput ? searchInput.value.trim().toLowerCase() : '';

  const activePill = $('.admin-queue-pill.active');
  const statusFilter = activePill ? activePill.dataset.status : 'All';

  let filtered = adminQueueTicketsList;
  if (statusFilter && statusFilter !== 'All') {
    filtered = filtered.filter(t => t.status === statusFilter);
  }
  if (searchVal) {
    filtered = filtered.filter(t =>
      (t.ticket_id && t.ticket_id.toLowerCase().includes(searchVal)) ||
      (t.subject && t.subject.toLowerCase().includes(searchVal)) ||
      (t.user_name && t.user_name.toLowerCase().includes(searchVal)) ||
      (t.user_email && t.user_email.toLowerCase().includes(searchVal))
    );
  }

  if (filtered.length === 0) {
    queueList.innerHTML = `<div style="padding: 2rem; text-align: center; color: var(--text-muted); font-size: 0.88rem;">No matching tickets found.</div>`;
    return;
  }

  queueList.innerHTML = filtered.map(t => {
    const isActive = t.id === currentAdminActiveTicketId;
    return `
      <div class="admin-queue-item ${isActive ? 'active' : ''}" data-ticket-id="${t.id}" onclick="selectAdminConversation(${t.id})">
        <div class="admin-queue-item-top">
          <span class="admin-queue-item-id">${escapeHtml(t.ticket_id)}</span>
          ${getStatusBadgeHtml(t.status)}
        </div>
        <div class="admin-queue-item-subj">${escapeHtml(t.subject)}</div>
        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.74rem; color: var(--text-muted);">
          <span><i class="fas fa-user" style="margin-right: 3px;"></i> ${escapeHtml(t.user_name || 'Customer')}</span>
          <span>${formatDateTime(t.created_at).split(' ')[0]}</span>
        </div>
      </div>
    `;
  }).join('');
}

async function selectAdminConversation(ticketId) {
  currentAdminActiveTicketId = ticketId;

  // Update active state in queue items
  $$('.admin-queue-item').forEach(el => {
    el.classList.toggle('active', parseInt(el.dataset.ticketId, 10) === ticketId);
  });

  const placeholder = $('#admin-convo-placeholder');
  const activeBox = $('#admin-convo-active-box');
  const scrollContainer = $('#admin-convo-messages-scroll');

  if (placeholder) placeholder.style.display = 'none';
  if (activeBox) activeBox.style.display = 'flex';
  if (scrollContainer) scrollContainer.innerHTML = `<div style="padding: 2rem; text-align: center; color: var(--text-muted);"><i class="fas fa-spinner fa-spin"></i> Loading conversation thread...</div>`;

  try {
    const res = await fetch(`/api/admin/support/tickets/${ticketId}/conversation`);
    if (!res.ok) throw new Error('Could not load ticket conversation');
    const data = await res.json();
    const t = data.ticket;
    const conversation = data.conversation || [];

    // Header info
    const idEl = $('#convo-ticket-id');
    const catEl = $('#convo-category-badge');
    const statusEl = $('#convo-status-badge');
    const subjEl = $('#convo-subject');
    const userEl = $('#convo-user-name');
    const emailEl = $('#convo-user-email');
    const dateEl = $('#convo-created-date');
    const statusSelect = $('#convo-quick-status');

    if (idEl) idEl.textContent = t.ticket_id;
    if (catEl) catEl.innerHTML = getCategoryBadgeHtml(t.category);
    if (statusEl) statusEl.innerHTML = getStatusBadgeHtml(t.status);
    if (subjEl) subjEl.textContent = t.subject;
    if (userEl) userEl.textContent = t.user_name || 'Customer';
    if (emailEl) emailEl.textContent = t.user_email || '';
    if (dateEl) dateEl.textContent = formatDateTime(t.created_at);
    if (statusSelect) statusSelect.value = t.status || 'Open';

    // Initial Request Card
    const initDesc = $('#convo-initial-description');
    const attachWrap = $('#convo-attachment-wrap');
    const attachImg = $('#convo-attachment-img');
    const attachLink = $('#convo-attachment-link');

    if (initDesc) initDesc.textContent = t.description;

    if (t.has_attachment && t.attachment_filename) {
      const fileUrl = `/api/support/attachments/${encodeURIComponent(t.attachment_filename)}`;
      if (attachWrap) attachWrap.style.display = 'block';
      if (attachImg) attachImg.src = fileUrl;
      if (attachLink) attachLink.href = fileUrl;
    } else {
      if (attachWrap) attachWrap.style.display = 'none';
    }

    // Render Messages Stream (Chronological)
    if (scrollContainer) {
      if (conversation.length <= 1) {
        scrollContainer.innerHTML = `
          <div style="text-align: center; padding: 2rem; color: var(--text-muted); font-size: 0.88rem;">
            <i class="fas fa-inbox" style="margin-bottom: 6px; font-size: 1.5rem; display: block; opacity: 0.5;"></i>
            Opening customer request received. No responses yet. Write a reply below.
          </div>
        `;
      } else {
        // Skip message index 0 because that is the initial description already shown above
        const replies = conversation.slice(1);
        scrollContainer.innerHTML = replies.map(msg => {
          const isAdmin = msg.sender_type === 'admin';
          return `
            <div class="admin-msg-bubble ${isAdmin ? 'admin-msg' : 'user-msg'}">
              <div class="admin-msg-header">
                <span class="admin-msg-sender">
                  <i class="fas ${isAdmin ? 'fa-shield-halved' : 'fa-user'}" style="color: ${isAdmin ? 'var(--accent)' : '#06b6d4'};"></i>
                  ${escapeHtml(msg.sender_name || (isAdmin ? 'Support Admin' : 'Customer'))}
                </span>
                <span class="admin-msg-time">${formatDateTime(msg.created_at)}</span>
              </div>
              <div style="white-space: pre-wrap; line-height: 1.6;">${escapeHtml(msg.message)}</div>
            </div>
          `;
        }).join('');
      }

      // Scroll to bottom of conversation
      scrollContainer.scrollTop = scrollContainer.scrollHeight;
    }

  } catch (err) {
    console.error('Error fetching conversation:', err);
    if (scrollContainer) {
      scrollContainer.innerHTML = `<div style="padding: 2rem; text-align: center; color: var(--danger);"><i class="fas fa-exclamation-circle"></i> Failed to load conversation details.</div>`;
    }
  }
}

// Send Admin Reply
async function handleAdminSendReply() {
  if (!currentAdminActiveTicketId) return;

  const textarea = $('#admin-reply-textarea');
  const statusSelect = $('#admin-reply-status-select');
  const sendBtn = $('#btn-admin-send-reply');

  const message = textarea ? textarea.value.trim() : '';
  const newStatus = statusSelect ? statusSelect.value : 'In Progress';

  if (!message) {
    showToast('Please type a reply message before sending', 'warning');
    if (textarea) textarea.focus();
    return;
  }

  if (sendBtn) {
    sendBtn.disabled = true;
    sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sending...';
  }

  try {
    const res = await fetch(`/api/admin/support/tickets/${currentAdminActiveTicketId}/reply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, status: newStatus })
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to send reply');

    showToast('Reply dispatched successfully!', 'success');
    if (textarea) textarea.value = '';

    // Reload active conversation and badges
    await selectAdminConversation(currentAdminActiveTicketId);
    updateAdminBadges();

    // Refresh tickets in cache
    const updatedTicket = adminQueueTicketsList.find(t => t.id === currentAdminActiveTicketId);
    if (updatedTicket) {
      updatedTicket.status = newStatus;
      renderAdminConvoQueue();
    }

  } catch (err) {
    console.error('Error sending reply:', err);
    showToast(err.message || 'Could not send reply. Try again.', 'error');
  } finally {
    if (sendBtn) {
      sendBtn.disabled = false;
      sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i> Send Reply';
    }
  }
}

// Helper to jump directly from any ticket row into Ticket Conversations
function openAdminConversation(ticketId) {
  switchView('admin-conversations');
  loadAdminConversations(ticketId);
}

// ── 8. User Support History Controller ──
async function loadAdminUserHistorySection() {
  const userSelect = $('#admin-user-select');
  if (!userSelect) return;

  try {
    userSelect.innerHTML = '<option value="">Loading users...</option>';
    const res = await fetch('/api/admin/support/users');
    if (!res.ok) throw new Error('Failed to load support users');
    const data = await res.json();
    adminUsersCache = data.users || [];

    if (adminUsersCache.length === 0) {
      userSelect.innerHTML = '<option value="">No registered users found</option>';
      return;
    }

    userSelect.innerHTML = '<option value="">Select a User to Inspect Support History...</option>' +
      adminUsersCache.map(u => {
        const ticketBadge = u.ticket_count > 0 ? `(${u.ticket_count} tickets)` : '(0 tickets)';
        return `<option value="${u.id}">${escapeHtml(u.full_name)} — ${escapeHtml(u.email)} ${ticketBadge}</option>`;
      }).join('');

    // Pre-select first user with tickets if available
    const firstWithTickets = adminUsersCache.find(u => u.ticket_count > 0);
    if (firstWithTickets) {
      userSelect.value = firstWithTickets.id;
      selectAdminUserHistory(firstWithTickets.id);
    }

  } catch (err) {
    console.error('Error loading support users:', err);
    userSelect.innerHTML = '<option value="">Error loading users</option>';
  }
}

async function selectAdminUserHistory(userId) {
  if (!userId) {
    const empty = $('#admin-user-history-empty');
    const content = $('#admin-user-history-content');
    if (empty) empty.style.display = 'block';
    if (content) content.style.display = 'none';
    return;
  }

  const empty = $('#admin-user-history-empty');
  const content = $('#admin-user-history-content');
  const tbody = $('#admin-user-tickets-tbody');

  if (empty) empty.style.display = 'none';
  if (content) content.style.display = 'block';
  if (tbody) tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 2rem; color: var(--text-muted);"><i class="fas fa-spinner fa-spin"></i> Loading user history...</td></tr>`;

  try {
    const res = await fetch(`/api/admin/support/users/${userId}/history`);
    if (!res.ok) throw new Error('Failed to load user history');
    const data = await res.json();
    const u = data.user;
    const stats = data.stats || {};
    const tickets = data.tickets || [];

    // Profile card
    const nameEl = $('#user-hist-name');
    const emailEl = $('#user-hist-email');
    const joinedEl = $('#user-hist-joined');
    const avatarEl = $('#user-hist-avatar');
    const totalEl = $('#user-hist-total');
    const openEl = $('#user-hist-open');
    const resolvedEl = $('#user-hist-resolved');
    const countEl = $('#user-hist-tickets-count');

    if (nameEl) nameEl.textContent = u.full_name;
    if (emailEl) emailEl.textContent = u.email;
    if (joinedEl) joinedEl.textContent = formatDateTime(u.created_at).split(' ')[0];
    if (avatarEl) avatarEl.textContent = (u.full_name || 'U').charAt(0).toUpperCase();

    if (totalEl) totalEl.textContent = stats.total_tickets || 0;
    if (openEl) openEl.textContent = stats.open_tickets || 0;
    if (resolvedEl) resolvedEl.textContent = stats.resolved_tickets || 0;
    if (countEl) countEl.textContent = tickets.length;

    // Render Tickets Table
    if (tbody) {
      if (tickets.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 2rem; color: var(--text-muted);">This user has not submitted any support tickets yet.</td></tr>`;
        return;
      }

      tbody.innerHTML = tickets.map(t => `
        <tr>
          <td style="font-weight: 700; color: var(--accent);"><i class="fas fa-ticket" style="margin-right: 4px; font-size: 0.8rem;"></i>${escapeHtml(t.ticket_id)}</td>
          <td>${getCategoryBadgeHtml(t.category)}</td>
          <td style="font-weight: 600; color: var(--text-primary); max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(t.subject)}</td>
          <td style="color: var(--text-secondary); font-size: 0.85rem;">${formatDateTime(t.created_at)}</td>
          <td><span class="admin-badge badge-active"><i class="fas fa-comments"></i> ${t.messages_count || 1} msgs</span></td>
          <td>${getStatusBadgeHtml(t.status)}</td>
          <td style="text-align: right;">
            <button type="button" class="btn-table-action" onclick="openAdminConversation(${t.id})" title="Open Conversation Thread">
              <i class="fas fa-comments" style="color: var(--accent);"></i>
            </button>
          </td>
        </tr>
      `).join('');
    }

  } catch (err) {
    console.error('Error fetching user history:', err);
    if (tbody) tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 2rem; color: var(--danger);"><i class="fas fa-exclamation-circle"></i> Error loading user history.</td></tr>`;
  }
}

// ── Attach Global Admin Event Listeners ──
function initAdminSuiteListeners() {
  // Top nav tab pills
  $$('.admin-tabs-nav .admin-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const targetView = btn.dataset.adminView;
      if (targetView) switchView(targetView);
    });
  });

  // Refresh buttons
  const btnRefDash = $('#btn-admin-refresh-dashboard');
  if (btnRefDash) btnRefDash.addEventListener('click', updateAdminBadges);

  const btnRefAll = $('#btn-admin-all-refresh');
  if (btnRefAll) btnRefAll.addEventListener('click', loadAdminAllTickets);

  const btnRefQueries = $('#btn-admin-queries-refresh');
  if (btnRefQueries) btnRefQueries.addEventListener('click', loadAdminGeneralQueries);

  const btnRefProblems = $('#btn-admin-problems-refresh');
  if (btnRefProblems) btnRefProblems.addEventListener('click', loadAdminReportedProblems);

  const btnRefFeatures = $('#btn-admin-features-refresh');
  if (btnRefFeatures) btnRefFeatures.addEventListener('click', loadAdminFeatureRequests);

  const btnRefUsers = $('#btn-admin-refresh-users');
  if (btnRefUsers) btnRefUsers.addEventListener('click', loadAdminUserHistorySection);

  // Filters with auto-reloading
  const allStatus = $('#admin-all-filter-status');
  if (allStatus) allStatus.addEventListener('change', loadAdminAllTickets);
  const allCat = $('#admin-all-filter-category');
  if (allCat) allCat.addEventListener('change', loadAdminAllTickets);
  const allSort = $('#admin-all-sort');
  if (allSort) allSort.addEventListener('change', loadAdminAllTickets);
  const allSearch = $('#admin-all-search');
  if (allSearch) allSearch.addEventListener('input', debounce(loadAdminAllTickets, 300));

  const qStatus = $('#admin-queries-filter-status');
  if (qStatus) qStatus.addEventListener('change', loadAdminGeneralQueries);
  const qSearch = $('#admin-queries-search');
  if (qSearch) qSearch.addEventListener('input', debounce(loadAdminGeneralQueries, 300));

  const pStatus = $('#admin-problems-filter-status');
  if (pStatus) pStatus.addEventListener('change', loadAdminReportedProblems);
  const pAttach = $('#admin-problems-filter-attachment');
  if (pAttach) pAttach.addEventListener('change', loadAdminReportedProblems);
  const pSearch = $('#admin-problems-search');
  if (pSearch) pSearch.addEventListener('input', debounce(loadAdminReportedProblems, 300));

  const fStatus = $('#admin-features-filter-status');
  if (fStatus) fStatus.addEventListener('change', loadAdminFeatureRequests);
  const fSearch = $('#admin-features-search');
  if (fSearch) fSearch.addEventListener('input', debounce(loadAdminFeatureRequests, 300));

  // Conversation queue pills
  $$('.admin-queue-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      $$('.admin-queue-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      renderAdminConvoQueue();
    });
  });

  const convoSearch = $('#admin-convo-queue-search');
  if (convoSearch) convoSearch.addEventListener('input', debounce(renderAdminConvoQueue, 200));

  // Quick templates in reply composer
  $$('.btn-template-pill').forEach(btn => {
    btn.addEventListener('click', () => {
      const textarea = $('#admin-reply-textarea');
      if (textarea) {
        textarea.value = btn.dataset.template;
        textarea.focus();
      }
    });
  });

  // Send reply button
  const sendReplyBtn = $('#btn-admin-send-reply');
  if (sendReplyBtn) sendReplyBtn.addEventListener('click', handleAdminSendReply);

  // Quick Status change from conversation header
  const quickStatus = $('#convo-quick-status');
  if (quickStatus) {
    quickStatus.addEventListener('change', async () => {
      if (!currentAdminActiveTicketId) return;
      const newStatus = quickStatus.value;
      try {
        const res = await fetch(`/api/admin/support/tickets/${currentAdminActiveTicketId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: newStatus })
        });
        if (res.ok) {
          showToast(`Status updated to ${newStatus}`, 'success');
          updateAdminBadges();
          const t = adminQueueTicketsList.find(x => x.id === currentAdminActiveTicketId);
          if (t) {
            t.status = newStatus;
            renderAdminConvoQueue();
          }
        }
      } catch (e) {
        showToast('Failed to update status', 'error');
      }
    });
  }

  // User History selector
  const userSelect = $('#admin-user-select');
  if (userSelect) {
    userSelect.addEventListener('change', () => {
      selectAdminUserHistory(parseInt(userSelect.value, 10));
    });
  }

  const userSearch = $('#admin-user-search-input');
  if (userSearch) {
    userSearch.addEventListener('input', debounce(() => {
      const q = userSearch.value.trim().toLowerCase();
      if (!userSelect) return;
      if (!q) {
        userSelect.innerHTML = '<option value="">Select a User...</option>' +
          adminUsersCache.map(u => `<option value="${u.id}">${escapeHtml(u.full_name)} — ${escapeHtml(u.email)} (${u.ticket_count} tickets)</option>`).join('');
      } else {
        const matches = adminUsersCache.filter(u =>
          (u.full_name && u.full_name.toLowerCase().includes(q)) ||
          (u.email && u.email.toLowerCase().includes(q))
        );
        userSelect.innerHTML = matches.map(u => `<option value="${u.id}">${escapeHtml(u.full_name)} — ${escapeHtml(u.email)} (${u.ticket_count} tickets)</option>`).join('');
        if (matches.length > 0) {
          userSelect.value = matches[0].id;
          selectAdminUserHistory(matches[0].id);
        }
      }
    }, 250));
  }
}

// Window exports for HTML inline handlers
window.openAdminConversation = openAdminConversation;
window.selectAdminConversation = selectAdminConversation;
window.loadAdminDashboard = loadAdminDashboard;
window.loadAdminAllTickets = loadAdminAllTickets;
window.loadAdminGeneralQueries = loadAdminGeneralQueries;
window.loadAdminReportedProblems = loadAdminReportedProblems;
window.loadAdminFeatureRequests = loadAdminFeatureRequests;
window.loadAdminConversations = loadAdminConversations;
window.loadAdminUserHistorySection = loadAdminUserHistorySection;
window.selectAdminUserHistory = selectAdminUserHistory;
window.updateAdminBadges = updateAdminBadges;

// ── Legacy loadAdminSupportTickets alias for compatibility ──
async function loadAdminSupportTickets() {
  await loadAdminAllTickets();
}


function initSupportSystem() {
  const categorySelect = $('#support-category');

  // ── Help & Support 4-Section Navigation Tabs ──
  function switchSupportSection(sectionName) {
    $$('#support-section-tabs .support-tab-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.section === sectionName);
    });
    $$('.support-section-pane').forEach(pane => {
      pane.classList.remove('active');
      pane.style.display = 'none';
    });
    const targetPane = $(`#pane-${sectionName}`);
    if (targetPane) {
      targetPane.classList.add('active');
      targetPane.style.display = 'block';
    }

    if (sectionName === 'faqs') {
      loadFAQs();
    } else if (sectionName === 'quick-help') {
      loadQuickQuestions();
    } else if (sectionName === 'tickets') {
      loadSupportTickets();
    }
  }
  window.switchSupportSection = switchSupportSection;

  $$('#support-section-tabs .support-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      switchSupportSection(btn.dataset.section);
    });
  });

  // Section Call-To-Action buttons to jump directly to Contact Support
  const btnFaqToContact = $('#btn-faq-to-contact');
  if (btnFaqToContact) {
    btnFaqToContact.addEventListener('click', () => {
      switchSupportSection('contact');
      const formCard = $('#support-form-container');
      if (formCard) formCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  const btnQuickToContact = $('#btn-quick-to-contact');
  if (btnQuickToContact) {
    btnQuickToContact.addEventListener('click', () => {
      switchSupportSection('contact');
      const formCard = $('#support-form-container');
      if (formCard) formCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  const btnEmptyToContact = $('#btn-empty-to-contact');
  if (btnEmptyToContact) {
    btnEmptyToContact.addEventListener('click', () => {
      switchSupportSection('contact');
    });
  }

  const btnTicketsNewReq = $('#btn-tickets-new-request');
  if (btnTicketsNewReq) {
    btnTicketsNewReq.addEventListener('click', () => {
      switchSupportSection('contact');
    });
  }

  // Description character count
  const descTextarea = $('#support-description');
  const charCountEl = $('#support-char-count');
  if (descTextarea && charCountEl) {
    descTextarea.addEventListener('input', () => {
      const len = descTextarea.value.length;
      charCountEl.textContent = `${len} / 4000 characters`;
      if (len > 3800) {
        charCountEl.style.color = '#ef4444';
      } else {
        charCountEl.style.color = 'var(--text-muted)';
      }
    });
  }

  // Attachment upload dropzone & input
  const dropzone = $('#attachment-dropzone');
  const fileInput = $('#support-attachment-input');
  const uploadPrompt = $('#upload-prompt');
  const previewBox = $('#attachment-preview');
  const previewImg = $('#attachment-preview-img');
  const previewFilename = $('#preview-filename');
  const previewFilesize = $('#preview-filesize');
  const btnRemove = $('#btn-remove-attachment');

  if (dropzone && fileInput) {
    dropzone.addEventListener('click', (e) => {
      if (e.target.closest('#btn-remove-attachment')) return;
      fileInput.click();
    });

    ['dragenter', 'dragover'].forEach(evt => {
      dropzone.addEventListener(evt, e => {
        e.preventDefault();
        dropzone.classList.add('drag-over');
      });
    });

    ['dragleave', 'drop'].forEach(evt => {
      dropzone.addEventListener(evt, e => {
        e.preventDefault();
        dropzone.classList.remove('drag-over');
      });
    });

    dropzone.addEventListener('drop', e => {
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleAttachmentSelect(e.dataTransfer.files[0]);
      }
    });

    fileInput.addEventListener('change', () => {
      if (fileInput.files && fileInput.files.length > 0) {
        handleAttachmentSelect(fileInput.files[0]);
      }
    });
  }

  function handleAttachmentSelect(file) {
    if (!file) return;

    // Validate type
    const validTypes = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'image/gif'];
    const ext = file.name.split('.').pop().toLowerCase();
    const validExts = ['png', 'jpg', 'jpeg', 'webp', 'gif'];

    if (!validTypes.includes(file.type) && !validExts.includes(ext)) {
      showToast('Please upload an approved image format (PNG, JPG, WEBP, GIF)', 'error');
      clearAttachment();
      return;
    }

    // Validate size (5 MB)
    if (file.size > 5 * 1024 * 1024) {
      showToast('Attachment exceeds maximum allowed size of 5 MB', 'error');
      clearAttachment();
      return;
    }

    activeTicketAttachment = file;
    if (previewFilename) previewFilename.textContent = file.name;
    if (previewFilesize) previewFilesize.textContent = `${(file.size / 1024).toFixed(1)} KB`;

    // Render preview
    const reader = new FileReader();
    reader.onload = e => {
      if (previewImg) previewImg.src = e.target.result;
      if (uploadPrompt) uploadPrompt.style.display = 'none';
      if (previewBox) previewBox.style.display = 'flex';
    };
    reader.readAsDataURL(file);
  }

  function clearAttachment() {
    activeTicketAttachment = null;
    if (fileInput) fileInput.value = '';
    if (previewImg) previewImg.src = '';
    if (previewBox) previewBox.style.display = 'none';
    if (uploadPrompt) uploadPrompt.style.display = 'flex';
  }

  if (btnRemove) {
    btnRemove.addEventListener('click', e => {
      e.stopPropagation();
      clearAttachment();
    });
  }

  // Support Form Submit
  const supportForm = $('#support-ticket-form');
  const btnSubmit = $('#btn-submit-support');
  const btnSubmitText = $('#btn-submit-support-text');

  if (supportForm) {
    supportForm.addEventListener('submit', async e => {
      e.preventDefault();

      const category = $('#support-category').value;
      const subject = $('#support-subject').value.trim();
      const description = $('#support-description').value.trim();

      if (!subject || subject.length < 3) {
        showToast('Subject must be at least 3 characters', 'error');
        return;
      }
      if (!description || description.length < 10) {
        showToast('Please provide a message of at least 10 characters', 'error');
        return;
      }

      const formData = new FormData();
      formData.append('category', category);
      formData.append('subject', subject);
      formData.append('description', description);
      if (activeTicketAttachment) {
        formData.append('attachment', activeTicketAttachment);
      }

      // Loading state
      btnSubmit.disabled = true;
      if (btnSubmitText) btnSubmitText.textContent = 'Submitting...';
      const icon = btnSubmit.querySelector('i');
      if (icon) icon.className = 'fas fa-spinner fa-spin';

      try {
        const resp = await fetch('/api/support/tickets', {
          method: 'POST',
          body: formData
        });
        const result = await resp.json();

        if (resp.ok) {
          showToast(`Support ticket created! Ref: ${result.ticket.ticket_id}`, 'success');
          supportForm.reset();
          clearAttachment();
          if (charCountEl) charCountEl.textContent = '0 / 4000 characters';
          if (categorySelect) categorySelect.value = 'General Query';
          loadSupportTickets();
          switchSupportSection('tickets');
        } else {
          showToast(result.error || 'Failed to submit support ticket', 'error');
        }
      } catch (err) {
        console.error('Error submitting ticket:', err);
        showToast('Network error while submitting ticket. Please try again.', 'error');
      } finally {
        btnSubmit.disabled = false;
        if (btnSubmitText) btnSubmitText.textContent = 'Submit Request';
        if (icon) icon.className = 'fas fa-paper-plane';
      }
    });
  }

  // Refresh user tickets button
  const btnRefreshUser = $('#btn-refresh-support-tickets');
  if (btnRefreshUser) {
    btnRefreshUser.addEventListener('click', () => {
      loadSupportTickets();
      showToast('Support tickets refreshed', 'info');
    });
  }

  // Modal close buttons
  const btnCloseModal = $('#btn-close-ticket-modal');
  const btnModalClose = $('#ticket-modal-close');
  const modalOverlay = $('#ticket-modal-overlay');

  if (btnCloseModal) btnCloseModal.addEventListener('click', closeTicketDetailsModal);
  if (btnModalClose) btnModalClose.addEventListener('click', closeTicketDetailsModal);
  if (modalOverlay) {
    modalOverlay.addEventListener('click', e => {
      if (e.target === modalOverlay) closeTicketDetailsModal();
    });
  }

  // Admin Controls
  const btnAdminRefresh = $('#btn-admin-refresh');
  if (btnAdminRefresh) {
    btnAdminRefresh.addEventListener('click', () => {
      loadAdminSupportTickets();
      showToast('Admin tickets refreshed', 'info');
    });
  }

  const adminSearchInput = $('#admin-search-input');
  if (adminSearchInput) {
    adminSearchInput.addEventListener('input', () => {
      clearTimeout(adminSearchDebounceTimer);
      adminSearchDebounceTimer = setTimeout(loadAdminSupportTickets, 300);
    });
  }

  const adminStatusFilter = $('#admin-filter-status');
  if (adminStatusFilter) {
    adminStatusFilter.addEventListener('change', loadAdminSupportTickets);
  }

  const adminCategoryFilter = $('#admin-filter-category');
  if (adminCategoryFilter) {
    adminCategoryFilter.addEventListener('change', loadAdminSupportTickets);
  }

  // Admin Save Ticket Changes
  const btnAdminSave = $('#btn-admin-save-ticket');
  if (btnAdminSave) {
    btnAdminSave.addEventListener('click', async () => {
      if (!currentViewingTicketId) return;

      const newStatus = $('#admin-update-status').value;
      const notes = $('#admin-update-notes').value;

      btnAdminSave.disabled = true;
      btnAdminSave.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';

      try {
        const resp = await fetch(`/api/admin/support/tickets/${currentViewingTicketId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: newStatus, admin_notes: notes })
        });
        const res = await resp.json();

        if (resp.ok) {
          showToast('Ticket updated successfully', 'success');
          closeTicketDetailsModal();
          loadAdminSupportTickets();
        } else {
          showToast(res.error || 'Failed to update ticket', 'error');
        }
      } catch (err) {
        console.error('Error updating ticket:', err);
        showToast('Network error while updating ticket', 'error');
      } finally {
        btnAdminSave.disabled = false;
        btnAdminSave.innerHTML = '<i class="fas fa-save"></i> Save Changes';
      }
    });
  }

  // Quick Questions Modal events
  const qqModalClose = $('#quick-question-modal-close');
  const btnCloseQqModal = $('#btn-close-quick-question-modal');
  const qqOverlay = $('#quick-question-modal-overlay');
  const btnQuickAskSupport = $('#btn-quick-ask-support');

  if (qqModalClose) qqModalClose.addEventListener('click', closeQuickQuestionModal);
  if (btnCloseQqModal) btnCloseQqModal.addEventListener('click', closeQuickQuestionModal);
  if (qqOverlay) {
    qqOverlay.addEventListener('click', (e) => {
      if (e.target === qqOverlay) closeQuickQuestionModal();
    });
  }
  if (btnQuickAskSupport) {
    btnQuickAskSupport.addEventListener('click', () => {
      closeQuickQuestionModal();
      switchSupportSection('contact');
      setTimeout(() => {
        const formCard = $('#support-form-container');
        if (formCard) {
          formCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
          const sub = $('#support-subject');
          if (sub) sub.focus();
        }
      }, 50);
    });
  }

  // FAQ Controls
  const faqSearchInput = $('#faq-search-input');
  const btnClearFaqSearch = $('#faq-search-clear');
  if (faqSearchInput) {
    faqSearchInput.addEventListener('input', () => {
      faqSearchKeyword = faqSearchInput.value.trim();
      if (btnClearFaqSearch) {
        btnClearFaqSearch.style.display = faqSearchKeyword ? 'block' : 'none';
      }
      clearTimeout(faqSearchDebounceTimer);
      faqSearchDebounceTimer = setTimeout(loadFAQs, 250);
    });
  }

  if (btnClearFaqSearch) {
    btnClearFaqSearch.addEventListener('click', () => {
      if (faqSearchInput) faqSearchInput.value = '';
      faqSearchKeyword = '';
      btnClearFaqSearch.style.display = 'none';
      loadFAQs();
      if (faqSearchInput) faqSearchInput.focus();
    });
  }

  // FAQ Category Pills
  $$('#faq-category-pills .faq-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      $$('#faq-category-pills .faq-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      activeFaqCategory = pill.dataset.category || 'All';
      loadFAQs();
    });
  });

  // Admin Section Tab Switching
  $$('.admin-tab-btn').forEach(tabBtn => {
    tabBtn.addEventListener('click', () => {
      $$('.admin-tab-btn').forEach(b => b.classList.remove('active'));
      tabBtn.classList.add('active');

      const targetTabId = tabBtn.dataset.tab;
      $$('.admin-tab-content').forEach(content => {
        if (content.id === targetTabId) {
          content.style.display = 'block';
        } else {
          content.style.display = 'none';
        }
      });

      if (targetTabId === 'admin-tab-faq') {
        loadAdminFAQs();
      } else if (targetTabId === 'admin-tab-qq') {
        loadAdminQuickQuestions();
      } else if (targetTabId === 'admin-tab-tickets') {
        loadAdminSupportTickets();
      }
    });
  });

  // Admin FAQ Controls
  const btnAdminAddFaq = $('#btn-admin-add-faq');
  const btnAdminRefreshFaq = $('#btn-admin-refresh-faq');
  const adminFaqSearchInput = $('#admin-faq-search-input');
  const adminFaqFilterCategory = $('#admin-faq-filter-category');
  const adminFaqForm = $('#admin-faq-form');
  const adminFaqModalClose = $('#admin-faq-modal-close');
  const btnCancelAdminFaq = $('#btn-cancel-admin-faq');

  if (btnAdminAddFaq) {
    btnAdminAddFaq.addEventListener('click', () => openAddFaqModal());
  }
  if (btnAdminRefreshFaq) {
    btnAdminRefreshFaq.addEventListener('click', () => {
      loadAdminFAQs();
      showToast('FAQs refreshed', 'info');
    });
  }
  if (adminFaqSearchInput) {
    adminFaqSearchInput.addEventListener('input', () => {
      clearTimeout(adminSearchDebounceTimer);
      adminSearchDebounceTimer = setTimeout(loadAdminFAQs, 300);
    });
  }
  if (adminFaqFilterCategory) {
    adminFaqFilterCategory.addEventListener('change', loadAdminFAQs);
  }
  if (adminFaqModalClose) adminFaqModalClose.addEventListener('click', closeAdminFaqModal);
  if (btnCancelAdminFaq) btnCancelAdminFaq.addEventListener('click', closeAdminFaqModal);
  if (adminFaqForm) {
    adminFaqForm.addEventListener('submit', handleAdminFaqSubmit);
  }

  // Admin Quick Question Controls
  const btnAdminAddQq = $('#btn-admin-add-qq');
  const btnAdminRefreshQq = $('#btn-admin-refresh-qq');
  const adminQqForm = $('#admin-qq-form');
  const adminQqModalClose = $('#admin-qq-modal-close');
  const btnCancelAdminQq = $('#btn-cancel-admin-qq');

  if (btnAdminAddQq) {
    btnAdminAddQq.addEventListener('click', () => openAddQqModal());
  }
  if (btnAdminRefreshQq) {
    btnAdminRefreshQq.addEventListener('click', () => {
      loadAdminQuickQuestions();
      showToast('Quick questions refreshed', 'info');
    });
  }
  if (adminQqModalClose) adminQqModalClose.addEventListener('click', closeAdminQqModal);
  if (btnCancelAdminQq) btnCancelAdminQq.addEventListener('click', closeAdminQqModal);
  if (adminQqForm) {
    adminQqForm.addEventListener('submit', handleAdminQqSubmit);
  }

  // Admin Delete Confirmation Modal Controls
  const adminDeleteModalClose = $('#admin-delete-modal-close');
  const btnCancelAdminDelete = $('#btn-cancel-admin-delete');
  const btnConfirmAdminDelete = $('#btn-confirm-admin-delete');

  if (adminDeleteModalClose) adminDeleteModalClose.addEventListener('click', closeAdminDeleteModal);
  if (btnCancelAdminDelete) btnCancelAdminDelete.addEventListener('click', closeAdminDeleteModal);
  if (btnConfirmAdminDelete) btnConfirmAdminDelete.addEventListener('click', executeAdminDelete);
}

// ── Quick Questions ──────────────────────────────────────────────
async function loadQuickQuestions() {
  const container = $('#quick-questions-grid');
  if (!container) return;

  try {
    const res = await fetch('/api/quick-questions');
    if (!res.ok) throw new Error('Failed to fetch quick questions');
    const data = await res.json();
    const questions = data.quick_questions || [];

    if (questions.length === 0) {
      container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 1.5rem; color: var(--text-muted);">No quick questions available.</div>`;
      return;
    }

    container.innerHTML = questions.map(qq => `
      <div class="quick-question-card" data-qq-id="${qq.id}" role="button" tabindex="0">
        <div class="qq-top">
          <div class="qq-icon">
            <i class="fas fa-bolt"></i>
          </div>
          <h4>${escapeHtml(qq.question)}</h4>
        </div>
        <div class="qq-footer">
          <span>Get Instant Answer</span>
          <i class="fas fa-arrow-right"></i>
        </div>
      </div>
    `).join('');

    container.querySelectorAll('.quick-question-card').forEach(card => {
      const qqId = parseInt(card.dataset.qqId, 10);
      const qqItem = questions.find(q => q.id === qqId);
      if (qqItem) {
        card.addEventListener('click', () => openQuickQuestionModal(qqItem));
        card.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            openQuickQuestionModal(qqItem);
          }
        });
      }
    });
  } catch (err) {
    console.error('Error loading quick questions:', err);
    container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 1rem; color: var(--danger);"><i class="fas fa-exclamation-circle"></i> Error loading quick questions</div>`;
  }
}

function openQuickQuestionModal(qqItem) {
  const overlay = $('#quick-question-modal-overlay');
  const titleEl = $('#quick-question-text');
  const bodyEl = $('#quick-question-answer');

  if (!overlay || !titleEl || !bodyEl) return;

  titleEl.textContent = qqItem.question;
  bodyEl.textContent = qqItem.answer;
  overlay.classList.add('active');
}

function closeQuickQuestionModal() {
  const overlay = $('#quick-question-modal-overlay');
  if (overlay) overlay.classList.remove('active');
}

// ── FAQs ─────────────────────────────────────────────────────────
let activeFaqCategory = 'All';
let faqSearchKeyword = '';
let faqSearchDebounceTimer = null;

async function loadFAQs() {
  const container = $('#faq-accordion-list');
  const emptyState = $('#faq-empty-state');
  if (!container) return;

  try {
    const params = new URLSearchParams();
    if (activeFaqCategory && activeFaqCategory !== 'All') {
      params.append('category', activeFaqCategory);
    }
    if (faqSearchKeyword) {
      params.append('q', faqSearchKeyword);
    }

    const res = await fetch(`/api/faq?${params.toString()}`);
    if (!res.ok) throw new Error('Failed to fetch FAQs');
    const data = await res.json();
    const faqs = data.faqs || [];

    if (faqs.length === 0) {
      container.innerHTML = '';
      if (emptyState) emptyState.style.display = 'block';
      return;
    }

    if (emptyState) emptyState.style.display = 'none';

    container.innerHTML = faqs.map(faq => `
      <div class="faq-accordion-item" data-faq-id="${faq.id}">
        <button type="button" class="faq-accordion-header" aria-expanded="false">
          <span class="faq-category-tag">${escapeHtml(faq.category)}</span>
          <span class="faq-question-text">${escapeHtml(faq.question)}</span>
          <i class="fas fa-chevron-down faq-chevron"></i>
        </button>
        <div class="faq-accordion-body">
          <div class="faq-answer-content">${escapeHtml(faq.answer)}</div>
        </div>
      </div>
    `).join('');

    container.querySelectorAll('.faq-accordion-header').forEach(header => {
      header.addEventListener('click', () => {
        const item = header.closest('.faq-accordion-item');
        const isOpen = item.classList.contains('open');

        if (isOpen) {
          item.classList.remove('open');
          header.setAttribute('aria-expanded', 'false');
        } else {
          item.classList.add('open');
          header.setAttribute('aria-expanded', 'true');
        }
      });
    });
  } catch (err) {
    console.error('Error loading FAQs:', err);
    if (container) {
      container.innerHTML = `<div style="text-align: center; padding: 2rem; color: var(--danger);"><i class="fas fa-exclamation-circle"></i> Error loading FAQs.</div>`;
    }
  }
}

// ── Admin FAQ & Quick Question Functions ─────────────────────────
let adminFaqsCache = [];
let adminQqCache = [];
let pendingDeleteTarget = null; // { type: 'faq' | 'qq', id: 123 }

async function loadAdminFAQs() {
  const tbody = $('#admin-faqs-tbody');
  const countBadge = $('#admin-faq-badge');
  const countHeader = $('#admin-faqs-count');
  const emptyState = $('#admin-faq-empty-state');
  const table = $('#admin-faqs-table');
  if (!tbody) return;

  const searchInput = $('#admin-faq-search-input');
  const categoryFilter = $('#admin-faq-filter-category');
  const q = searchInput ? searchInput.value.trim() : '';
  const category = categoryFilter ? categoryFilter.value : 'All';

  try {
    const params = new URLSearchParams();
    if (category && category !== 'All') params.append('category', category);
    if (q) params.append('q', q);

    const res = await fetch(`/api/admin/faq?${params.toString()}`);
    if (!res.ok) throw new Error('Failed to load admin FAQs');
    const data = await res.json();
    adminFaqsCache = data.faqs || [];

    if (countBadge) countBadge.textContent = adminFaqsCache.length;
    if (countHeader) countHeader.textContent = adminFaqsCache.length;

    if (adminFaqsCache.length === 0) {
      tbody.innerHTML = '';
      if (emptyState) emptyState.style.display = 'block';
      if (table) table.style.display = 'none';
      return;
    }

    if (emptyState) emptyState.style.display = 'none';
    if (table) table.style.display = 'table';

    tbody.innerHTML = adminFaqsCache.map(faq => {
      const pubBadge = faq.is_published
        ? `<span class="admin-badge badge-published"><i class="fas fa-check-circle"></i> Published</span>`
        : `<span class="admin-badge badge-draft"><i class="fas fa-eye-slash"></i> Draft</span>`;
      const dateStr = formatDateTime(faq.updated_at || faq.created_at);

      return `
        <tr>
          <td>
            <div style="font-weight: 600; color: var(--text-primary);">${escapeHtml(faq.question)}</div>
            <div style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 4px; max-height: 2.8em; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;">${escapeHtml(faq.answer)}</div>
          </td>
          <td><span class="faq-category-tag">${escapeHtml(faq.category)}</span></td>
          <td>${pubBadge}</td>
          <td style="font-size: 0.82rem; color: var(--text-muted);">${dateStr}</td>
          <td style="text-align: right; white-space: nowrap;">
            <button type="button" class="btn-table-action" onclick="openEditFaqModal(${faq.id})" title="Edit FAQ">
              <i class="fas fa-pencil"></i>
            </button>
            <button type="button" class="btn-table-action toggle-action ${faq.is_published ? 'published' : 'unpublished'}" onclick="toggleFaqPublish(${faq.id})" title="${faq.is_published ? 'Unpublish FAQ' : 'Publish FAQ'}">
              <i class="fas ${faq.is_published ? 'fa-eye' : 'fa-eye-slash'}"></i>
            </button>
            <button type="button" class="btn-table-action delete-action" onclick="confirmDeleteFaq(${faq.id})" title="Delete FAQ">
              <i class="fas fa-trash"></i>
            </button>
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error('Error loading admin FAQs:', err);
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding: 2rem; color: var(--danger);"><i class="fas fa-exclamation-circle"></i> Error loading FAQs.</td></tr>`;
  }
}

async function loadAdminQuickQuestions() {
  const tbody = $('#admin-qq-tbody');
  const countBadge = $('#admin-qq-badge');
  const countHeader = $('#admin-qq-count');
  const emptyState = $('#admin-qq-empty-state');
  const table = $('#admin-qq-table');
  if (!tbody) return;

  try {
    const res = await fetch('/api/admin/quick-questions');
    if (!res.ok) throw new Error('Failed to load quick questions');
    const data = await res.json();
    adminQqCache = data.quick_questions || [];

    if (countBadge) countBadge.textContent = adminQqCache.length;
    if (countHeader) countHeader.textContent = adminQqCache.length;

    if (adminQqCache.length === 0) {
      tbody.innerHTML = '';
      if (emptyState) emptyState.style.display = 'block';
      if (table) table.style.display = 'none';
      return;
    }

    if (emptyState) emptyState.style.display = 'none';
    if (table) table.style.display = 'table';

    tbody.innerHTML = adminQqCache.map((qq, idx) => {
      const activeBadge = qq.is_active
        ? `<span class="admin-badge badge-active"><i class="fas fa-check"></i> Active</span>`
        : `<span class="admin-badge badge-inactive"><i class="fas fa-ban"></i> Inactive</span>`;
      const isFirst = idx === 0;
      const isLast = idx === adminQqCache.length - 1;

      return `
        <tr>
          <td>
            <div class="order-controls">
              <span style="font-weight: 700; min-width: 20px; font-size: 0.85rem;">#${qq.display_order}</span>
              <button type="button" class="btn-order" onclick="moveQuickQuestion(${qq.id}, -1)" ${isFirst ? 'disabled' : ''} title="Move Up">
                <i class="fas fa-chevron-up"></i>
              </button>
              <button type="button" class="btn-order" onclick="moveQuickQuestion(${qq.id}, 1)" ${isLast ? 'disabled' : ''} title="Move Down">
                <i class="fas fa-chevron-down"></i>
              </button>
            </div>
          </td>
          <td style="font-weight: 600; color: var(--text-primary);">${escapeHtml(qq.question)}</td>
          <td style="font-size: 0.85rem; color: var(--text-secondary); max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(qq.answer)}</td>
          <td>${activeBadge}</td>
          <td style="text-align: right; white-space: nowrap;">
            <button type="button" class="btn-table-action" onclick="openEditQqModal(${qq.id})" title="Edit Quick Question">
              <i class="fas fa-pencil"></i>
            </button>
            <button type="button" class="btn-table-action toggle-action ${qq.is_active ? 'published' : 'unpublished'}" onclick="toggleQqActive(${qq.id})" title="${qq.is_active ? 'Deactivate' : 'Activate'}">
              <i class="fas ${qq.is_active ? 'fa-toggle-on' : 'fa-toggle-off'}"></i>
            </button>
            <button type="button" class="btn-table-action delete-action" onclick="confirmDeleteQq(${qq.id})" title="Delete Quick Question">
              <i class="fas fa-trash"></i>
            </button>
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error('Error loading admin quick questions:', err);
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding: 2rem; color: var(--danger);"><i class="fas fa-exclamation-circle"></i> Error loading quick questions.</td></tr>`;
  }
}

// FAQ Modal handlers
function openAddFaqModal() {
  const overlay = $('#admin-faq-modal-overlay');
  const title = $('#admin-faq-modal-title');
  const idInput = $('#admin-faq-id');
  const form = $('#admin-faq-form');
  if (!overlay || !form) return;

  form.reset();
  if (idInput) idInput.value = '';
  if (title) title.textContent = 'Add New FAQ';
  const pubCheckbox = $('#admin-faq-published');
  if (pubCheckbox) pubCheckbox.checked = true;
  overlay.classList.add('active');
}

function openEditFaqModal(id) {
  const faq = adminFaqsCache.find(f => f.id === id);
  if (!faq) return;

  const overlay = $('#admin-faq-modal-overlay');
  const title = $('#admin-faq-modal-title');
  const idInput = $('#admin-faq-id');
  const catInput = $('#admin-faq-category');
  const qInput = $('#admin-faq-question');
  const aInput = $('#admin-faq-answer');
  const pubInput = $('#admin-faq-published');

  if (!overlay) return;

  if (title) title.textContent = 'Edit FAQ';
  if (idInput) idInput.value = faq.id;
  if (catInput) catInput.value = faq.category;
  if (qInput) qInput.value = faq.question;
  if (aInput) aInput.value = faq.answer;
  if (pubInput) pubInput.checked = Boolean(faq.is_published);

  overlay.classList.add('active');
}

function closeAdminFaqModal() {
  const overlay = $('#admin-faq-modal-overlay');
  if (overlay) overlay.classList.remove('active');
}

async function handleAdminFaqSubmit(e) {
  e.preventDefault();
  const id = $('#admin-faq-id').value;
  const category = $('#admin-faq-category').value;
  const question = $('#admin-faq-question').value.trim();
  const answer = $('#admin-faq-answer').value.trim();
  const is_published = $('#admin-faq-published').checked;

  if (!question || question.length < 3) {
    showToast('Question must be at least 3 characters', 'error');
    return;
  }
  if (!answer || answer.length < 5) {
    showToast('Answer must be at least 5 characters', 'error');
    return;
  }

  const payload = { category, question, answer, is_published };
  const url = id ? `/api/admin/faq/${id}` : '/api/admin/faq';
  const method = id ? 'PATCH' : 'POST';

  try {
    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const result = await res.json();
    if (res.ok) {
      showToast(result.message || 'FAQ saved successfully', 'success');
      closeAdminFaqModal();
      loadAdminFAQs();
      loadFAQs();
    } else {
      showToast(result.error || 'Failed to save FAQ', 'error');
    }
  } catch (err) {
    console.error('Error saving FAQ:', err);
    showToast('Network error while saving FAQ', 'error');
  }
}

async function toggleFaqPublish(id) {
  const faq = adminFaqsCache.find(f => f.id === id);
  if (!faq) return;

  const nextStatus = !faq.is_published;
  try {
    const res = await fetch(`/api/admin/faq/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_published: nextStatus })
    });
    const result = await res.json();
    if (res.ok) {
      showToast(`FAQ ${nextStatus ? 'published' : 'unpublished'}`, 'success');
      loadAdminFAQs();
      loadFAQs();
    } else {
      showToast(result.error || 'Failed to update FAQ status', 'error');
    }
  } catch (err) {
    console.error('Error toggling FAQ publish:', err);
    showToast('Network error updating FAQ', 'error');
  }
}

function confirmDeleteFaq(id) {
  const faq = adminFaqsCache.find(f => f.id === id);
  if (!faq) return;

  pendingDeleteTarget = { type: 'faq', id: faq.id, label: faq.question };
  const overlay = $('#admin-delete-modal-overlay');
  const title = $('#admin-delete-modal-title');
  const msg = $('#admin-delete-modal-message');

  if (title) title.textContent = 'Delete FAQ';
  if (msg) msg.textContent = `Are you sure you want to delete the FAQ: "${faq.question}"? This action cannot be undone.`;
  if (overlay) overlay.classList.add('active');
}

// Quick Questions Modal handlers
function openAddQqModal() {
  const overlay = $('#admin-qq-modal-overlay');
  const title = $('#admin-qq-modal-title');
  const idInput = $('#admin-qq-id');
  const form = $('#admin-qq-form');
  if (!overlay || !form) return;

  form.reset();
  if (idInput) idInput.value = '';
  if (title) title.textContent = 'Add Quick Question';
  const orderInput = $('#admin-qq-order');
  if (orderInput) orderInput.value = adminQqCache.length + 1;
  const activeInput = $('#admin-qq-active');
  if (activeInput) activeInput.checked = true;

  overlay.classList.add('active');
}

function openEditQqModal(id) {
  const qq = adminQqCache.find(q => q.id === id);
  if (!qq) return;

  const overlay = $('#admin-qq-modal-overlay');
  const title = $('#admin-qq-modal-title');
  const idInput = $('#admin-qq-id');
  const qInput = $('#admin-qq-question');
  const orderInput = $('#admin-qq-order');
  const aInput = $('#admin-qq-answer');
  const activeInput = $('#admin-qq-active');

  if (!overlay) return;

  if (title) title.textContent = 'Edit Quick Question';
  if (idInput) idInput.value = qq.id;
  if (qInput) qInput.value = qq.question;
  if (orderInput) orderInput.value = qq.display_order;
  if (aInput) aInput.value = qq.answer;
  if (activeInput) activeInput.checked = Boolean(qq.is_active);

  overlay.classList.add('active');
}

function closeAdminQqModal() {
  const overlay = $('#admin-qq-modal-overlay');
  if (overlay) overlay.classList.remove('active');
}

async function handleAdminQqSubmit(e) {
  e.preventDefault();
  const id = $('#admin-qq-id').value;
  const question = $('#admin-qq-question').value.trim();
  const answer = $('#admin-qq-answer').value.trim();
  const orderVal = $('#admin-qq-order').value;
  const is_active = $('#admin-qq-active').checked;

  if (!question || question.length < 3) {
    showToast('Question must be at least 3 characters', 'error');
    return;
  }
  if (!answer || answer.length < 5) {
    showToast('Answer must be at least 5 characters', 'error');
    return;
  }

  const payload = {
    question,
    answer,
    display_order: orderVal ? parseInt(orderVal, 10) : undefined,
    is_active
  };

  const url = id ? `/api/admin/quick-questions/${id}` : '/api/admin/quick-questions';
  const method = id ? 'PATCH' : 'POST';

  try {
    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const result = await res.json();
    if (res.ok) {
      showToast(result.message || 'Quick Question saved successfully', 'success');
      closeAdminQqModal();
      loadAdminQuickQuestions();
      loadQuickQuestions();
    } else {
      showToast(result.error || 'Failed to save Quick Question', 'error');
    }
  } catch (err) {
    console.error('Error saving Quick Question:', err);
    showToast('Network error while saving Quick Question', 'error');
  }
}

async function toggleQqActive(id) {
  const qq = adminQqCache.find(q => q.id === id);
  if (!qq) return;

  const nextStatus = !qq.is_active;
  try {
    const res = await fetch(`/api/admin/quick-questions/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_active: nextStatus })
    });
    const result = await res.json();
    if (res.ok) {
      showToast(`Quick Question ${nextStatus ? 'activated' : 'deactivated'}`, 'success');
      loadAdminQuickQuestions();
      loadQuickQuestions();
    } else {
      showToast(result.error || 'Failed to update Quick Question status', 'error');
    }
  } catch (err) {
    console.error('Error toggling Quick Question status:', err);
    showToast('Network error updating Quick Question', 'error');
  }
}

function confirmDeleteQq(id) {
  const qq = adminQqCache.find(q => q.id === id);
  if (!qq) return;

  pendingDeleteTarget = { type: 'qq', id: qq.id, label: qq.question };
  const overlay = $('#admin-delete-modal-overlay');
  const title = $('#admin-delete-modal-title');
  const msg = $('#admin-delete-modal-message');

  if (title) title.textContent = 'Delete Quick Question';
  if (msg) msg.textContent = `Are you sure you want to delete the Quick Question: "${qq.question}"? This action cannot be undone.`;
  if (overlay) overlay.classList.add('active');
}

async function moveQuickQuestion(id, direction) {
  const idx = adminQqCache.findIndex(q => q.id === id);
  if (idx < 0) return;

  const targetIdx = idx + direction;
  if (targetIdx < 0 || targetIdx >= adminQqCache.length) return;

  // Swap in array
  const temp = adminQqCache[idx];
  adminQqCache[idx] = adminQqCache[targetIdx];
  adminQqCache[targetIdx] = temp;

  const orderIds = adminQqCache.map(q => q.id);

  try {
    const res = await fetch('/api/admin/quick-questions/reorder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ order: orderIds })
    });
    if (res.ok) {
      showToast('Order updated', 'info');
      loadAdminQuickQuestions();
      loadQuickQuestions();
    } else {
      showToast('Failed to update order', 'error');
    }
  } catch (err) {
    console.error('Error reordering quick questions:', err);
    showToast('Network error reordering questions', 'error');
  }
}

function closeAdminDeleteModal() {
  const overlay = $('#admin-delete-modal-overlay');
  if (overlay) overlay.classList.remove('active');
  pendingDeleteTarget = null;
}

async function executeAdminDelete() {
  if (!pendingDeleteTarget) return;

  const { type, id } = pendingDeleteTarget;
  const btn = $('#btn-confirm-admin-delete');
  if (btn) btn.disabled = true;

  try {
    const url = type === 'faq' ? `/api/admin/faq/${id}` : `/api/admin/quick-questions/${id}`;
    const res = await fetch(url, { method: 'DELETE' });
    const result = await res.json();

    if (res.ok) {
      showToast(result.message || 'Item deleted successfully', 'success');
      closeAdminDeleteModal();
      if (type === 'faq') {
        loadAdminFAQs();
        loadFAQs();
      } else {
        loadAdminQuickQuestions();
        loadQuickQuestions();
      }
    } else {
      showToast(result.error || 'Failed to delete item', 'error');
    }
  } catch (err) {
    console.error('Error deleting item:', err);
    showToast('Network error deleting item', 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

// Expose global functions for HTML onclick attributes
window.openEditFaqModal = openEditFaqModal;
window.toggleFaqPublish = toggleFaqPublish;
window.confirmDeleteFaq = confirmDeleteFaq;
window.openEditQqModal = openEditQqModal;
window.toggleQqActive = toggleQqActive;
window.confirmDeleteQq = confirmDeleteQq;
window.moveQuickQuestion = moveQuickQuestion;

// ── App Init ───────────────────────────────────────────────────
function initApp() {
  initTheme();

  // Initialize event listeners safely
  try {
    initSupportSystem();
  } catch (err) {
    console.error('initSupportSystem error:', err);
  }

  try {
    initAdminSuiteListeners();
  } catch (err) {
    console.error('initAdminSuiteListeners error:', err);
  }

  // Determine target view from URL query parameter or body data-active-view
  const urlParams = new URLSearchParams(window.location.search);
  const targetView = urlParams.get('view') || (document.body && document.body.dataset ? document.body.dataset.activeView : 'dashboard') || 'dashboard';

  switchView(targetView);

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
