// ══════════════════════════════════════════════════════════════════
// ExpenseFlow — App Logic
// ══════════════════════════════════════════════════════════════════

const API = '/api';
const CATEGORIES = {
  Food:          { icon: 'fa-utensils',       color: '#f97316' },
  Transport:     { icon: 'fa-car',            color: '#3b82f6' },
  Shopping:      { icon: 'fa-bag-shopping',   color: '#ec4899' },
  Bills:         { icon: 'fa-file-invoice',   color: '#eab308' },
  Entertainment: { icon: 'fa-film',           color: '#8b5cf6' },
  Health:        { icon: 'fa-heartbeat',      color: '#22c55e' },
  Education:     { icon: 'fa-graduation-cap', color: '#06b6d4' },
  Other:         { icon: 'fa-box',            color: '#64748b' }
};

let trendChart = null;
let categoryChart = null;
let deleteTargetId = null;

// ── Helpers ────────────────────────────────────────────────────
function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }

function formatCurrency(n) {
  return '$' + Number(n).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

function formatDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function showToast(message, type = 'success') {
  const container = $('#toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  const icons = { success: 'fa-check-circle', error: 'fa-exclamation-circle', info: 'fa-info-circle' };
  toast.innerHTML = `<i class="fas ${icons[type]}"></i> ${message}`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.animation = 'slideOut .3s forwards';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// ── Navigation ─────────────────────────────────────────────────
function switchView(viewName) {
  $$('.view').forEach(v => v.classList.remove('active'));
  $$('.nav-item').forEach(n => n.classList.remove('active'));
  $(`#view-${viewName}`).classList.add('active');
  $(`[data-view="${viewName}"]`).classList.add('active');
  window.scrollTo({ top: 0, behavior: 'instant' });
  if (viewName === 'dashboard') loadDashboard();
  else loadExpenses();
}

$$('.nav-item').forEach(item => {
  item.addEventListener('click', e => {
    e.preventDefault();
    switchView(item.dataset.view);
    // Close mobile sidebar
    $('#sidebar').classList.remove('open');
  });
});

$('#view-all-link').addEventListener('click', e => {
  e.preventDefault();
  switchView('expenses');
});

// Mobile menu
$('#menu-toggle').addEventListener('click', () => {
  $('#sidebar').classList.toggle('open');
});

$('#btn-add-mobile').addEventListener('click', () => openModal());

// ── Dashboard ──────────────────────────────────────────────────
async function loadDashboard() {
  try {
    const res = await fetch(`${API}/stats`);
    const stats = await res.json();

    $('#stat-total-value').textContent = formatCurrency(stats.total);
    $('#stat-monthly-value').textContent = formatCurrency(stats.monthly);
    $('#stat-daily-value').textContent = formatCurrency(stats.daily_avg);
    $('#stat-top-value').textContent = stats.top_category;

    renderTrendChart(stats.daily_trend);
    renderCategoryChart(stats.category_breakdown);
    loadRecentExpenses();
  } catch (err) {
    showToast('Failed to load dashboard', 'error');
  }
}

function renderTrendChart(data) {
  const ctx = $('#trendChart').getContext('2d');
  const labels = Object.keys(data).map(d => {
    const date = new Date(d + 'T00:00:00');
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  });
  const values = Object.values(data);

  if (trendChart) trendChart.destroy();

  const gradient = ctx.createLinearGradient(0, 0, 0, 250);
  gradient.addColorStop(0, 'rgba(139, 92, 246, 0.3)');
  gradient.addColorStop(1, 'rgba(139, 92, 246, 0.0)');

  trendChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Daily Spending',
        data: values,
        borderColor: '#8b5cf6',
        backgroundColor: gradient,
        borderWidth: 2,
        fill: true,
        tension: 0.4,
        pointRadius: 0,
        pointHoverRadius: 6,
        pointHoverBackgroundColor: '#8b5cf6',
        pointHoverBorderColor: '#fff',
        pointHoverBorderWidth: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(17, 24, 39, 0.9)',
          titleColor: '#f1f5f9',
          bodyColor: '#94a3b8',
          borderColor: 'rgba(255,255,255,0.1)',
          borderWidth: 1,
          padding: 12,
          displayColors: false,
          callbacks: {
            label: ctx => formatCurrency(ctx.raw)
          }
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: { color: '#64748b', font: { size: 10 }, maxTicksLimit: 8 }
        },
        y: {
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: {
            color: '#64748b', font: { size: 10 },
            callback: v => '$' + v
          }
        }
      }
    }
  });
}

function renderCategoryChart(data) {
  const ctx = $('#categoryChart').getContext('2d');
  const labels = Object.keys(data);
  const values = Object.values(data);
  const colors = labels.map(l => CATEGORIES[l]?.color || '#64748b');

  if (categoryChart) categoryChart.destroy();

  categoryChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: colors,
        borderColor: 'rgba(17, 24, 39, 0.8)',
        borderWidth: 3,
        hoverOffset: 8
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '65%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            color: '#94a3b8', padding: 15, font: { size: 11 },
            usePointStyle: true, pointStyleWidth: 8
          }
        },
        tooltip: {
          backgroundColor: 'rgba(17, 24, 39, 0.9)',
          titleColor: '#f1f5f9',
          bodyColor: '#94a3b8',
          borderColor: 'rgba(255,255,255,0.1)',
          borderWidth: 1,
          padding: 12,
          callbacks: {
            label: ctx => `${ctx.label}: ${formatCurrency(ctx.raw)}`
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

    if (recent.length === 0) {
      list.innerHTML = '<div class="empty-state"><i class="fas fa-receipt"></i><p>No expenses yet</p></div>';
      return;
    }

    list.innerHTML = recent.map(e => {
      const cat = CATEGORIES[e.category] || CATEGORIES.Other;
      return `
        <div class="recent-item">
          <div class="recent-item-icon" style="background:${cat.color}20;color:${cat.color}">
            <i class="fas ${cat.icon}"></i>
          </div>
          <div class="recent-item-info">
            <div class="recent-item-desc">${e.description}</div>
            <div class="recent-item-date">${formatDate(e.date)} · ${e.category}</div>
          </div>
          <div class="recent-item-amount">-${formatCurrency(e.amount)}</div>
        </div>
      `;
    }).join('');
  } catch (err) {
    console.error('Failed to load recent expenses:', err);
  }
}

// ── Expenses List ──────────────────────────────────────────────
async function loadExpenses() {
  try {
    const params = new URLSearchParams();
    const cat = $('#filter-category').value;
    const search = $('#search-input').value;
    const startDate = $('#filter-start-date').value;
    const endDate = $('#filter-end-date').value;
    const sort = $('#filter-sort').value;

    if (cat !== 'All') params.append('category', cat);
    if (search) params.append('search', search);
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    params.append('sort', sort);

    const res = await fetch(`${API}/expenses?${params}`);
    const expenses = await res.json();
    renderExpensesTable(expenses);
  } catch (err) {
    showToast('Failed to load expenses', 'error');
  }
}

function renderExpensesTable(expenses) {
  const tbody = $('#expenses-tbody');

  if (expenses.length === 0) {
    tbody.innerHTML = `
      <tr><td colspan="5">
        <div class="empty-state">
          <i class="fas fa-receipt"></i>
          <p>No expenses found</p>
        </div>
      </td></tr>`;
    $('#table-info').textContent = 'Showing 0 expenses';
    $('#table-total').textContent = 'Total: $0.00';
    return;
  }

  const total = expenses.reduce((s, e) => s + e.amount, 0);
  tbody.innerHTML = expenses.map(e => {
    const cat = CATEGORIES[e.category] || CATEGORIES.Other;
    const catClass = e.category.toLowerCase();
    return `
      <tr>
        <td>${formatDate(e.date)}</td>
        <td><span class="category-badge ${catClass}"><i class="fas ${cat.icon}"></i> ${e.category}</span></td>
        <td>${e.description}</td>
        <td class="amount-cell">-${formatCurrency(e.amount)}</td>
        <td>
          <div class="action-btns">
            <button class="btn-icon edit" onclick="editExpense(${e.id})" title="Edit"><i class="fas fa-pen"></i></button>
            <button class="btn-icon delete" onclick="confirmDelete(${e.id})" title="Delete"><i class="fas fa-trash"></i></button>
          </div>
        </td>
      </tr>
    `;
  }).join('');

  $('#table-info').textContent = `Showing ${expenses.length} expense${expenses.length > 1 ? 's' : ''}`;
  $('#table-total').textContent = `Total: ${formatCurrency(total)}`;
}

// Filter event listeners
let filterTimeout;
$('#search-input').addEventListener('input', () => {
  clearTimeout(filterTimeout);
  filterTimeout = setTimeout(loadExpenses, 300);
});
$('#filter-category').addEventListener('change', loadExpenses);
$('#filter-start-date').addEventListener('change', loadExpenses);
$('#filter-end-date').addEventListener('change', loadExpenses);
$('#filter-sort').addEventListener('change', loadExpenses);

// ── Modal ──────────────────────────────────────────────────────
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
  } else {
    $('#modal-title').innerHTML = '<i class="fas fa-plus-circle"></i> Add Expense';
    $('#btn-save').innerHTML = '<i class="fas fa-check"></i> Save Expense';
    $('#expense-date').value = new Date().toISOString().split('T')[0];
  }

  overlay.classList.add('active');
}

function closeModal() {
  $('#modal-overlay').classList.remove('active');
}

$('#modal-close').addEventListener('click', closeModal);
$('#btn-cancel').addEventListener('click', closeModal);
$('#modal-overlay').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeModal();
});

// Add expense buttons
$('#btn-add-expense').addEventListener('click', () => openModal());
$('#btn-add-expense-2').addEventListener('click', () => openModal());

// ── Save Expense ───────────────────────────────────────────────
$('#expense-form').addEventListener('submit', async e => {
  e.preventDefault();

  const id = $('#expense-id').value;
  const categoryRadio = document.querySelector('input[name="category"]:checked');

  if (!categoryRadio) {
    showToast('Please select a category', 'error');
    return;
  }

  const data = {
    amount: parseFloat($('#expense-amount').value),
    category: categoryRadio.value,
    description: $('#expense-description').value.trim(),
    date: $('#expense-date').value
  };

  if (!data.amount || data.amount <= 0) {
    showToast('Please enter a valid amount', 'error');
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

    if (!res.ok) throw new Error('Failed to save');

    closeModal();
    showToast(id ? 'Expense updated!' : 'Expense added!', 'success');
    loadDashboard();
    loadExpenses();
  } catch (err) {
    showToast('Failed to save expense', 'error');
  }
});

// ── Edit Expense ───────────────────────────────────────────────
window.editExpense = async function(id) {
  try {
    const res = await fetch(`${API}/expenses`);
    const expenses = await res.json();
    const expense = expenses.find(e => e.id === id);
    if (expense) openModal(expense);
  } catch (err) {
    showToast('Failed to load expense', 'error');
  }
};

// ── Delete Expense ─────────────────────────────────────────────
window.confirmDelete = function(id) {
  deleteTargetId = id;
  $('#delete-modal-overlay').classList.add('active');
};

function closeDeleteModal() {
  $('#delete-modal-overlay').classList.remove('active');
  deleteTargetId = null;
}

$('#delete-modal-close').addEventListener('click', closeDeleteModal);
$('#btn-cancel-delete').addEventListener('click', closeDeleteModal);
$('#delete-modal-overlay').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeDeleteModal();
});

$('#btn-confirm-delete').addEventListener('click', async () => {
  if (!deleteTargetId) return;
  try {
    const res = await fetch(`${API}/expenses/${deleteTargetId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete');

    closeDeleteModal();
    showToast('Expense deleted!', 'success');
    loadDashboard();
    loadExpenses();
  } catch (err) {
    showToast('Failed to delete expense', 'error');
  }
});

// ── Export CSV ──────────────────────────────────────────────────
$('#btn-export').addEventListener('click', () => {
  window.location.href = `${API}/export`;
  showToast('Downloading CSV...', 'info');
});

// ── Init ───────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadDashboard();
});
