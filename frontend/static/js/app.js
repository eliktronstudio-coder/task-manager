/* ===== Глобальные утилиты ===== */
const API = window.location.origin + '/api';
const tg = window.Telegram?.WebApp;
const inTelegram = !!tg?.initData;

function setupTelegram() {
  if (!inTelegram) return;
  tg.ready();
  tg.expand();
  tg.setHeaderColor?.('#0d6efd');
  if (tg.colorScheme === 'dark') document.documentElement.setAttribute('data-bs-theme', 'dark');
}

// Вне Telegram (отладка в браузере при DEBUG=true на сервере): ?debug_tg_user_id=123
function debugUserId() {
  const fromUrl = new URLSearchParams(window.location.search).get('debug_tg_user_id');
  try {
    if (fromUrl) localStorage.setItem('debug_tg_user_id', fromUrl);
    return fromUrl || localStorage.getItem('debug_tg_user_id');
  } catch (e) {
    return fromUrl;
  }
}

function startTaskId() {
  const fromUrl = new URLSearchParams(window.location.search).get('task_id');
  const startParam = tg?.initDataUnsafe?.start_param || '';
  const id = fromUrl || (startParam.startsWith('task_') ? startParam.slice(5) : null);
  return id ? parseInt(id) : null;
}

// Файлы и Excel открываем во внешнем браузере — встроенный в Telegram не всегда умеет скачивать
function openExternal(e) {
  if (!inTelegram) return;
  e.preventDefault();
  tg.openLink(new URL(e.currentTarget.getAttribute('href'), window.location.origin).href);
}

async function api(method, path, body = null, isFormData = false) {
  const opts = { method, headers: {} };
  if (inTelegram) {
    opts.headers['X-Telegram-Init-Data'] = tg.initData;
  } else if (debugUserId()) {
    opts.headers['X-Debug-Tg-User-Id'] = debugUserId();
  }
  if (body && !isFormData) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  } else if (isFormData) {
    opts.body = body;
  }
  const r = await fetch(API + path, opts);
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(err.detail || r.statusText);
  }
  if (r.status === 204) return null;
  return r.json();
}

function formatDate(d) {
  if (!d) return '—';
  const dt = new Date(d);
  return dt.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function isOverdue(task) {
  if (!task.deadline) return false;
  return new Date(task.deadline) < new Date() && task.status !== 'closed';
}

function statusLabel(s) {
  const m = { in_progress: 'В работе', critical: 'Критично', closed: 'Закрыто' };
  return m[s] || s;
}

function statusBadgeClass(s) {
  const m = { in_progress: 'bg-primary', critical: 'bg-danger', closed: 'bg-success' };
  return m[s] || 'bg-secondary';
}

function positionLabel(p) {
  return { noz: 'НОЗ', is: 'ИС' }[p] || '';
}

function employeeLabel(e) {
  return e.position ? `${e.full_name} · ${positionLabel(e.position)}` : e.full_name;
}

function sectionLabel(s) {
  const m = { preparation: 'Подготовка исходников', delivery: 'Поставки', quality: 'Качество открытия' };
  return m[s] || s;
}

function taskCardClass(task) {
  if (task.status === 'critical') return 'task-critical';
  if (isOverdue(task)) return 'task-overdue';
  if (task.status === 'closed') return 'task-closed';
  return '';
}

/* ===== Главное приложение ===== */
function taskApp() {
  return {
    loading: true,
    page: 'home',
    prevPage: 'home',
    currentEmployee: null,
    taskList: [],
    adminTaskList: [],
    stores: [],
    employees: [],
    counts: { in_progress: 0, critical: 0, overdue: 0 },
    activeFilter: {},
    adminFilter: {},
    showFilter: false,
    selectedTaskId: null,
    toastMsg: '',
    toastType: 'success',

    // Утилиты
    formatDate, statusLabel, statusBadgeClass, sectionLabel, taskCardClass, isOverdue, employeeLabel,

    async init() {
      setupTelegram();
      this.setupBackButton();

      try {
        this.currentEmployee = await api('GET', '/me');
        [this.employees, this.stores] = await Promise.all([
          api('GET', '/employees/'),
          api('GET', '/stores/'),
        ]);
        await this.loadCounts();

        const taskId = startTaskId();
        if (taskId) this.openTask(taskId);
      } catch (e) {
        this.showToast(e.message, 'danger');
      }
      this.loading = false;
    },

    setupBackButton() {
      if (!inTelegram) return;
      tg.BackButton.onClick(() => {
        if (this.page === 'task_detail') {
          this.page = this.prevPage === 'task_detail' ? 'tasks' : this.prevPage;
          if (this.page === 'tasks') this.loadTasks();
        } else {
          this.page = 'home';
        }
      });
      this.$watch('page', p => p === 'home' ? tg.BackButton.hide() : tg.BackButton.show());
    },

    async loadCounts() {
      if (!this.currentEmployee) return;
      const id = this.currentEmployee.id;
      const [inWork, critical, overdue] = await Promise.all([
        api('GET', `/tasks/?assignee_id=${id}&status=in_progress`),
        api('GET', `/tasks/?assignee_id=${id}&status=critical`),
        api('GET', `/tasks/?assignee_id=${id}&overdue_only=true`),
      ]);
      this.counts = {
        in_progress: inWork.length,
        critical: critical.length,
        overdue: overdue.length,
      };
    },

    async loadTasks() {
      if (!this.currentEmployee) return;
      const params = new URLSearchParams({ assignee_id: this.currentEmployee.id });
      if (this.activeFilter.status) params.set('status', this.activeFilter.status);
      if (this.activeFilter.section) params.set('section', this.activeFilter.section);
      if (this.activeFilter.store_id) params.set('store_id', this.activeFilter.store_id);
      if (this.activeFilter.overdue_only === 'true') params.set('overdue_only', 'true');
      this.taskList = await api('GET', '/tasks/?' + params.toString());
    },

    async loadAllTasks() {
      const params = new URLSearchParams();
      if (this.adminFilter.assignee_id) params.set('assignee_id', this.adminFilter.assignee_id);
      if (this.adminFilter.store_id) params.set('store_id', this.adminFilter.store_id);
      const tasks = await api('GET', '/tasks/?' + params.toString());
      // ИС видит здесь только чужие задачи — свои у него в «Мои задачи»
      this.adminTaskList = this.currentEmployee?.is_manager
        ? tasks
        : tasks.filter(t => t.assignee?.id !== this.currentEmployee?.id);
    },

    filterAndGo(status) {
      if (status === 'overdue') {
        this.activeFilter = { overdue_only: 'true' };
      } else {
        this.activeFilter = { status };
      }
      this.page = 'tasks';
      this.loadTasks();
    },

    openTask(id) {
      this.selectedTaskId = id;
      if (this.page !== 'task_detail') this.prevPage = this.page;
      this.page = 'task_detail';
      window.dispatchEvent(new CustomEvent('open-task'));
    },

    async openEmployees() {
      this.employees = await api('GET', '/employees/');
      this.page = 'employees';
    },

    async setPosition(employee, value) {
      try {
        const updated = await api('PATCH', `/employees/${employee.id}`, { position: value || null });
        Object.assign(employee, updated);
        this.showToast(value ? `Должность: ${positionLabel(value)}` : 'Должность снята');
      } catch (e) {
        this.showToast('Ошибка: ' + e.message, 'danger');
        this.employees = await api('GET', '/employees/');
      }
    },

    exportUrl() {
      const params = new URLSearchParams();
      if (this.adminFilter.store_id) params.set('store_id', this.adminFilter.store_id);
      if (this.adminFilter.assignee_id) params.set('assignee_id', this.adminFilter.assignee_id);
      return `/api/export/tasks.xlsx?${params}`;
    },

    showToast(msg, type = 'success') {
      this.toastMsg = msg;
      this.toastType = type;
      const el = this.$refs.toast;
      if (el) {
        const t = bootstrap.Toast.getOrCreateInstance(el, { delay: 3000 });
        t.show();
      }
    },
  };
}

/* ===== Детали задачи ===== */
function taskDetailApp() {
  return {
    task: null,
    comments: [],
    history: [],
    newComment: '',
    editDeadline: false,
    newDeadline: '',
    showHistory: false,

    formatDate, statusLabel, statusBadgeClass, sectionLabel, employeeLabel,

    async loadDetail() {
      const id = this.selectedTaskId;
      if (!id) return;
      this.task = null;
      this.comments = [];
      this.history = [];
      try {
        [this.task, this.comments, this.history] = await Promise.all([
          api('GET', `/tasks/${id}`),
          api('GET', `/tasks/${id}/comments/`),
          api('GET', `/tasks/${id}/history`),
        ]);
      } catch (e) {
        this.showToast('Ошибка загрузки задачи', 'danger');
      }
    },

    canEdit() {
      const emp = this.currentEmployee;
      if (!emp) return false;
      if (emp.is_manager) return true;
      return this.task?.assignee?.id === emp.id;
    },

    canTake() {
      const emp = this.currentEmployee;
      return !!(emp?.can_take_tasks && this.task && this.task.status !== 'closed'
        && this.task.assignee?.id !== emp.id);
    },

    async takeTask() {
      try {
        this.task = await api('POST', `/tasks/${this.task.id}/take`);
        this.showToast('Задача теперь ваша');
        this.history = await api('GET', `/tasks/${this.task.id}/history`);
        await this.loadCounts();
      } catch (e) {
        this.showToast('Ошибка: ' + e.message, 'danger');
      }
    },

    async changeStatus(status) {
      const emp = this.currentEmployee;
      try {
        this.task = await api('PATCH', `/tasks/${this.task.id}`, { status });
        this.showToast('Статус изменён');
        await this.loadDetail();
      } catch (e) {
        this.showToast('Ошибка: ' + e.message, 'danger');
      }
    },

    async saveDeadline() {
      const emp = this.currentEmployee;
      if (!this.newDeadline) return;
      const deadline = new Date(this.newDeadline).toISOString();
      try {
        this.task = await api('PATCH', `/tasks/${this.task.id}`, { deadline });
        this.editDeadline = false;
        this.showToast('Срок изменён');
      } catch (e) {
        this.showToast('Ошибка: ' + e.message, 'danger');
      }
    },

    async submitComment() {
      const emp = this.currentEmployee;
      if (!this.newComment && (!this.$refs.fileInput?.files?.length)) return;
      try {
        const fd = new FormData();
        if (this.newComment) fd.append('text', this.newComment);
        const files = this.$refs.fileInput?.files || [];
        for (const f of files) fd.append('files', f);

        await api('POST', `/tasks/${this.task.id}/comments/`, fd, true);
        this.newComment = '';
        if (this.$refs.fileInput) this.$refs.fileInput.value = '';
        this.comments = await api('GET', `/tasks/${this.task.id}/comments/`);
        this.showToast('Комментарий добавлен');
      } catch (e) {
        this.showToast('Ошибка: ' + e.message, 'danger');
      }
    },

    async addPresetReminder(preset) {
      try {
        await api('POST', `/tasks/${this.task.id}/reminders/preset?preset=${preset}`);
        this.task = await api('GET', `/tasks/${this.task.id}`);
        this.showToast('Напоминание добавлено');
      } catch (e) {
        this.showToast('Ошибка: ' + e.message, 'danger');
      }
    },

    presetLabel(p) {
      const m = { '1h': 'за 1ч', '2h': 'за 2ч', '3h': 'за 3ч', '1d': 'за 1д', '2d': 'за 2д', '3d': 'за 3д' };
      return m[p] || p;
    },

    attachmentUrl(taskId, commentId, attId) {
      return `${API}/tasks/${taskId}/comments/${commentId}/attachments/${attId}`;
    },

    historyField(f) {
      const m = { status: 'статус', assignee_id: 'исполнитель', deadline: 'срок', created: 'создана', comment: 'комментарий' };
      return m[f] || f;
    },
  };
}

/* ===== Создание задачи ===== */
function createTaskApp() {
  return {
    form: { store_id: '', section: '', title: '', description: '', assignee_id: '', deadline: '' },
    templates: [],
    selectedTemplate: '',
    submitting: false,

    get sectionTemplates() {
      if (!this.form.section) return [];
      return this.templates.filter(t => t.section === this.form.section);
    },

    async loadForm() {
      this.templates = await api('GET', '/templates/');
    },

    applyTemplate() {
      if (!this.selectedTemplate) return;
      const t = this.templates.find(t => t.id == this.selectedTemplate);
      if (t) {
        this.form.title = t.name;
        this.form.subsection = t.subsection || '';
      }
    },

    async submitTask() {
      if (!this.form.store_id || !this.form.section || !this.form.title) {
        this.showToast('Заполните обязательные поля', 'warning');
        return;
      }
      this.submitting = true;
      const emp = this.currentEmployee;
      const body = {
        store_id: parseInt(this.form.store_id),
        section: this.form.section,
        title: this.form.title,
        description: this.form.description || null,
        assignee_id: this.form.assignee_id ? parseInt(this.form.assignee_id) : (emp?.id || null),
        deadline: this.form.deadline ? new Date(this.form.deadline).toISOString() : null,
        template_id: this.selectedTemplate ? parseInt(this.selectedTemplate) : null,
      };
      if (!body.assignee_id && emp) body.assignee_id = emp.id;

      try {
        await api('POST', '/tasks/', body);
        this.showToast('Задача создана!');
        this.page = 'tasks';
        this.activeFilter = {};
        await this.loadTasks();
        await this.loadCounts();
      } catch (e) {
        this.showToast('Ошибка: ' + e.message, 'danger');
      }
      this.submitting = false;
    },
  };
}

/* ===== Настройки ===== */
function settingsApp() {
  return {
    ns: {},
    timezone: 'Europe/Moscow',
    saving: false,
    notifTypes: [
      ['notify_new_task', 'Новая задача назначена мне'],
      ['notify_status_change', 'Изменён статус задачи'],
      ['notify_deadline_change', 'Изменён срок задачи'],
      ['notify_new_comment', 'Новый комментарий'],
      ['notify_critical', 'Задача стала критичной'],
      ['notify_overdue', 'Задача просрочена'],
    ],

    async loadSettings() {
      const emp = this.currentEmployee;
      if (!emp) return;
      const full = await api('GET', `/employees/${emp.id}`);
      this.ns = { ...(full.notification_settings || {}) };
      this.timezone = full.timezone || 'Europe/Moscow';
    },

    async saveSettings() {
      const emp = this.currentEmployee;
      if (!emp) return;
      this.saving = true;
      try {
        await Promise.all([
          api('PATCH', `/employees/${emp.id}/notifications`, this.ns),
          api('PATCH', `/employees/${emp.id}`, { timezone: this.timezone }),
        ]);
        this.currentEmployee.timezone = this.timezone;
        this.showToast('Настройки сохранены');
        this.page = 'home';
      } catch (e) {
        this.showToast('Ошибка: ' + e.message, 'danger');
      }
      this.saving = false;
    },
  };
}
