(function () {
  const taskListEl = document.getElementById("task-list");
  const goalInput = document.getElementById("goal");
  const taskTitleInput = document.getElementById("task-title");
  const reviewSummary = document.getElementById("review-summary");
  const reviewEfficiency = document.getElementById("review-efficiency");
  const reviewTomorrow = document.getElementById("review-tomorrow");

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  // ---------- Auth & fetch 封装 ----------
  const TOKEN_KEY = "ai_study_token";
  const USERNAME_KEY = "ai_study_username";
  const META_BASE = (() => {
    const meta = document.querySelector("meta[name='app-base']");
    return meta && meta.content ? meta.content : "";
  })();

  function normalizeBase(base) {
    let out = (base || "").trim();
    if (!out) return "/";
    if (!out.startsWith("/")) out = "/" + out;
    if (!out.endsWith("/")) out += "/";
    return out;
  }

  function getLocationBase() {
    const p = window.location.pathname || "/";
    if (p.endsWith("/")) return p;
    const last = p.split("/").pop() || "";
    if (last.includes(".")) return p.slice(0, p.lastIndexOf("/") + 1) || "/";
    return p + "/";
  }

  const LOCATION_BASE = normalizeBase(getLocationBase());
  const API_BASE = (() => {
    const normalizedMeta = normalizeBase(META_BASE);
    if (normalizedMeta !== "/") return normalizedMeta;
    return LOCATION_BASE;
  })();

  function getToken() {
    return window.localStorage.getItem(TOKEN_KEY);
  }

  function setToken(token, username) {
    if (token) {
      window.localStorage.setItem(TOKEN_KEY, token);
      if (username) window.localStorage.setItem(USERNAME_KEY, username);
    } else {
      window.localStorage.removeItem(TOKEN_KEY);
      window.localStorage.removeItem(USERNAME_KEY);
    }
    syncAuthUI();
  }

  function buildApiCandidates(path) {
    if (/^https?:\/\//i.test(path || "")) return [path];
    const clean = (path || "").replace(/^\/+/, "");
    const bases = [API_BASE, LOCATION_BASE, "/"];
    const seen = new Set();
    const urls = [];
    for (const base of bases) {
      const normalized = normalizeBase(base);
      const full = normalized + clean;
      if (!seen.has(full)) {
        seen.add(full);
        urls.push(full);
      }
    }
    return urls;
  }

  async function apiFetch(url, options = {}) {
    const token = getToken();
    const headers = options.headers ? { ...options.headers } : {};
    if (token) headers["Authorization"] = "Bearer " + token;
    const requestOptions = { ...options, headers };
    let lastError = null;
    for (const candidate of buildApiCandidates(url)) {
      try {
        return await fetch(candidate, requestOptions);
      } catch (err) {
        lastError = err;
      }
    }
    throw lastError || new Error("fetch failed");
  }

  async function apiJson(url, options = {}) {
    const res = await apiFetch(url, options);
    const raw = await res.text();
    let data = {};
    try {
      data = raw ? JSON.parse(raw) : {};
    } catch (_e) {
      data = {};
    }
    if (!res.ok) {
      throw new Error(data.detail || raw || `请求失败（${res.status}）`);
    }
    return data;
  }

  function syncAuthUI() {
    const username = window.localStorage.getItem(USERNAME_KEY);
    const span = document.getElementById("auth-username");
    const loginBtn = document.getElementById("btn-open-auth");
    const logoutBtn = document.getElementById("btn-logout");
    if (!span || !loginBtn || !logoutBtn) return;
    if (getToken()) {
      span.textContent = username ? `Hi，${username}` : "";
      loginBtn.style.display = "none";
      logoutBtn.style.display = "inline-flex";
    } else {
      span.textContent = "";
      loginBtn.style.display = "inline-flex";
      logoutBtn.style.display = "none";
    }
  }

  async function ensureLoggedIn() {
    if (getToken()) return true;
    const modal = document.getElementById("auth-modal");
    if (modal) modal.classList.add("show");
    return false;
  }

  // 登录弹窗交互
  (function initAuth() {
    const modal = document.getElementById("auth-modal");
    const openBtn = document.getElementById("btn-open-auth");
    const closeBtn = document.getElementById("btn-auth-close");
    const loginBtn = document.getElementById("btn-auth-login");
    const registerBtn = document.getElementById("btn-auth-register");
    const logoutBtn = document.getElementById("btn-logout");
    const userInput = document.getElementById("auth-username-input");
    const passInput = document.getElementById("auth-password-input");
    const errorEl = document.getElementById("auth-error");

    function openModal() {
      if (!modal) return;
      modal.classList.add("show");
      errorEl.textContent = "";
      setTimeout(() => userInput && userInput.focus(), 0);
    }

    function closeModal() {
      if (!modal) return;
      modal.classList.remove("show");
      userInput.value = "";
      passInput.value = "";
      errorEl.textContent = "";
    }

    async function handleAuth(path) {
      const username = userInput.value.trim();
      const password = passInput.value;
      if (!username || !password) {
        errorEl.textContent = "请输入用户名和密码";
        return;
      }
      try {
        const data = await apiJson(path, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password }),
        });
        if (!data.access_token) {
          errorEl.textContent = "返回数据异常，请稍后重试";
          return;
        }
        setToken(data.access_token, data.username);
        closeModal();
        // 登录后刷新数据
        loadAll();
      } catch (e) {
        errorEl.textContent = e.message || "网络错误，请稍后再试";
      }
    }

    if (openBtn) openBtn.onclick = openModal;
    if (closeBtn) closeBtn.onclick = closeModal;
    if (loginBtn) loginBtn.onclick = () => handleAuth("/auth/login");
    if (registerBtn) registerBtn.onclick = () => handleAuth("/auth/register");
    if (logoutBtn) logoutBtn.onclick = () => {
      setToken(null);
      loadAll();
    };

    syncAuthUI();
  })();

  // ---------- PWA ----------
  (function initPwa() {
    if ("serviceWorker" in navigator) {
      window.addEventListener("load", () => {
        navigator.serviceWorker.register("/service-worker.js").catch(() => {});
      });
    }
    let deferredPrompt = null;
    const installBtn = document.getElementById("btn-install-app");
    window.addEventListener("beforeinstallprompt", (e) => {
      e.preventDefault();
      deferredPrompt = e;
      if (installBtn) installBtn.style.display = "inline-flex";
    });
    if (installBtn) {
      installBtn.addEventListener("click", async () => {
        if (!deferredPrompt) return;
        deferredPrompt.prompt();
        await deferredPrompt.userChoice;
        deferredPrompt = null;
        installBtn.style.display = "none";
      });
    }
  })();

  // ---------- 任务列表 ----------
  async function loadTasks() {
    if (!(await ensureLoggedIn())) return;
    const res = await apiFetch("/tasks");
    const tasks = await res.json();
    if (tasks.length === 0) {
      taskListEl.innerHTML = '<li class="empty-msg">暂无任务</li>';
      taskListEl.classList.add("empty");
    } else {
      taskListEl.classList.remove("empty");
      taskListEl.innerHTML = tasks
        .map(
          (t) =>
            `<li class="task-item" data-id="${t.id}" data-completed="${t.completed}">
          <label class="task-check">
            <input type="checkbox" ${t.completed ? "checked" : ""} data-id="${t.id}">
            <span class="task-title ${t.completed ? "done" : ""}">${escapeHtml(t.title)}</span>
          </label>
          <button type="button" class="btn-icon btn-delete" data-id="${t.id}" title="删除">×</button>
        </li>`
        )
        .join("");
    }
    taskListEl.querySelectorAll(".task-check input").forEach((cb) => {
      cb.addEventListener("change", (e) => toggleTask(parseInt(e.target.dataset.id, 10)));
    });
    taskListEl.querySelectorAll(".btn-delete").forEach((btn) => {
      btn.addEventListener("click", (e) => deleteTask(parseInt(e.currentTarget.dataset.id, 10)));
    });
    refreshStats();
    if (window.calendar) calendar.refetchEvents();
  }

  async function toggleTask(id) {
    const li = taskListEl.querySelector(`.task-item[data-id="${id}"]`);
    const checkbox = li?.querySelector("input[type=checkbox]");
    const checked = checkbox?.checked ?? false;
    await apiFetch(`/task/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ completed: checked }) });
    const titleSpan = li?.querySelector(".task-title");
    if (titleSpan) titleSpan.classList.toggle("done", checked);
    refreshStats();
  }

  async function deleteTask(id) {
    await apiFetch(`/task/${id}`, { method: "DELETE" });
    loadTasks();
  }

  document.getElementById("btn-add").onclick = async () => {
    const title = taskTitleInput.value.trim();
    if (!title) return;
    await apiFetch("/task", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    taskTitleInput.value = "";
    loadTasks();
  };

  taskTitleInput.onkeydown = (e) => {
    if (e.key === "Enter") document.getElementById("btn-add").click();
  };

  // ---------- 统计与图表 ----------
  let chartInstance = null;

  async function refreshStats() {
    if (!(await ensureLoggedIn())) return;
    const s = await apiJson("/stats");
    document.getElementById("stat-total").textContent = s.total_tasks;
    document.getElementById("stat-done").textContent = s.completed_tasks;
    document.getElementById("stat-rate").textContent = s.completion_rate + "%";
    if (chartInstance) {
      chartInstance.data.datasets[0].data = [s.completed_tasks, s.total_tasks - s.completed_tasks];
      chartInstance.update();
    }
  }

  function initChart() {
    const ctx = document.getElementById("chart").getContext("2d");
    chartInstance = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: ["已完成", "未完成"],
        datasets: [{ data: [0, 0], backgroundColor: ["#0d9488", "#e5e2dc"] }],
      },
      options: { responsive: true, plugins: { legend: { position: "bottom" } } },
    });
    refreshStats();
  }

  async function loadEfficiencyPanel() {
    if (!(await ensureLoggedIn())) return;
    try {
      const data = await apiJson("/analytics/efficiency");
      document.getElementById("eff-completion").textContent = `${data.completion_rate || 0}%`;
      document.getElementById("eff-focus").textContent = data.focus_score ?? 0;
      document.getElementById("eff-delay").textContent = data.procrastination_index ?? 0;
    } catch (_e) {}
  }

  function renderReportCard(report) {
    const target = document.getElementById("report-content");
    if (!target) return;
    const m = report.metrics || {};
    target.textContent =
      `${report.title || "学习报告"}（${report.period_start || ""} ~ ${report.period_end || ""}）\n` +
      `完成率：${m.completion_rate || 0}%\n` +
      `专注度：${m.focus_score || 0}\n` +
      `拖延指数：${m.procrastination_index || 0}\n` +
      `逾期任务数：${m.overdue_count || 0}\n\n` +
      `待处理任务：${(report.open_tasks || []).join("、") || "无"}\n` +
      `建议：\n- ${(report.suggestions || []).join("\n- ") || "保持学习节奏"}`;
  }

  const weeklyBtn = document.getElementById("btn-weekly-report");
  if (weeklyBtn) {
    weeklyBtn.onclick = async () => {
      if (!(await ensureLoggedIn())) return;
      const report = await apiJson("/reports/weekly");
      renderReportCard(report);
    };
  }
  const monthlyBtn = document.getElementById("btn-monthly-report");
  if (monthlyBtn) {
    monthlyBtn.onclick = async () => {
      if (!(await ensureLoggedIn())) return;
      const report = await apiJson("/reports/monthly");
      renderReportCard(report);
    };
  }

  // ---------- FullCalendar ----------
  const calendarEl = document.getElementById("calendar");
  let calendar = null;
  if (calendarEl) {
    calendar = new FullCalendar.Calendar(calendarEl, {
      locale: "zh-cn",
      initialView: "dayGridMonth",
      headerToolbar: { left: "prev,next today", center: "title", right: "dayGridMonth,listWeek" },
      events: (info, success, failure) => {
        if (!getToken()) {
          success([]);
          return;
        }
        apiFetch("/events")
          .then((r) => r.json())
          .then(success)
          .catch(failure);
      },
      eventContent: function (arg) {
        const completed = arg.event.extendedProps.completed;
        return { html: `<span class="fc-event-title ${completed ? "completed" : ""}">${escapeHtml(arg.event.title)}</span>` };
      },
    });
    calendar.render();
    window.calendar = calendar;

    // 强制保证 today 按钮回到当前日期
    const todayBtn = calendarEl.querySelector(".fc-today-button");
    if (todayBtn) {
      todayBtn.addEventListener("click", () => {
        calendar.today();
      });
    }
  }

  // ---------- AI 计划 ----------
  document.getElementById("btn-plan").onclick = async () => {
    const goal = goalInput.value.trim();
    if (!goal) return;
    const btn = document.getElementById("btn-plan");
    btn.disabled = true;
    btn.textContent = "生成中…";
    try {
      if (!(await ensureLoggedIn())) return;
      await apiFetch("/ai_plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal }),
      });
      goalInput.value = "";
      loadTasks();
    } finally {
      btn.disabled = false;
      btn.textContent = "生成计划";
    }
  };
  goalInput.onkeydown = (e) => {
    if (e.key === "Enter") document.getElementById("btn-plan").click();
  };

  // ---------- 长期目标 ----------
  async function loadGoals() {
    if (!(await ensureLoggedIn())) return;
    const goals = await apiJson("/goals");
    const ul = document.getElementById("goal-list");
    ul.innerHTML = goals.map((g) => `<li>${escapeHtml(g.title)}</li>`).join("");
  }

  document.getElementById("btn-goal").onclick = async () => {
    const input = document.getElementById("goal-long");
    const title = input.value.trim();
    if (!title) return;
    const btn = document.getElementById("btn-goal");
    btn.disabled = true;
    btn.textContent = "拆解中…";
    try {
      if (!(await ensureLoggedIn())) return;
      await apiFetch("/goal", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
      input.value = "";
      loadGoals();
      loadTasks();
    } finally {
      btn.disabled = false;
      btn.textContent = "拆解目标";
    }
  };
  loadGoals();

  // ---------- 每日复盘 ----------
  document.getElementById("btn-review").onclick = async () => {
    const btn = document.getElementById("btn-review");
    reviewSummary.textContent = "";
    reviewEfficiency.textContent = "";
    reviewTomorrow.textContent = "";
    reviewSummary.classList.add("review-loading");
    btn.disabled = true;
    try {
      if (!(await ensureLoggedIn())) return;
      const data = await apiJson("/review", { method: "POST" });
      reviewSummary.textContent = data.summary || "—";
      reviewEfficiency.textContent = data.efficiency || "—";
      reviewTomorrow.textContent = data.tomorrow_plan || "—";
    } catch (e) {
      reviewSummary.textContent = "生成失败，请稍后重试";
    } finally {
      reviewSummary.classList.remove("review-loading");
      btn.disabled = false;
    }
  };

  // ---------- 番茄钟 ----------
  const pomoDisplay = document.getElementById("pomodoro-display");
  let pomoSeconds = 25 * 60;
  let pomoTimer = null;

  function formatPomo(s) {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return m + ":" + (sec < 10 ? "0" : "") + sec;
  }

  document.getElementById("btn-pomo-start").onclick = () => {
    if (pomoTimer) return;
    pomoTimer = setInterval(() => {
      pomoSeconds--;
      pomoDisplay.textContent = formatPomo(pomoSeconds);
      if (pomoSeconds <= 0) {
        clearInterval(pomoTimer);
        pomoTimer = null;
        pomoSeconds = 25 * 60;
        pomoDisplay.textContent = "25:00";
        if (Notification.permission === "granted") new Notification("番茄钟", { body: "一个番茄钟结束，休息一下吧～" });
      }
    }, 1000);
  };

  document.getElementById("btn-pomo-stop").onclick = () => {
    if (pomoTimer) clearInterval(pomoTimer);
    pomoTimer = null;
    pomoSeconds = 25 * 60;
    pomoDisplay.textContent = "25:00";
  };

  // ---------- 浏览器通知 ----------
  document.getElementById("btn-notify").onclick = () => {
    if (!("Notification" in window)) {
      alert("当前浏览器不支持通知");
      return;
    }
    if (Notification.permission === "granted") {
      new Notification("AI 学习系统", { body: "通知已开启" });
      return;
    }
    Notification.requestPermission();
  };

  // ---------- 作业上传 ----------
  async function loadAssignments() {
    if (!(await ensureLoggedIn())) return;
    const list = await apiJson("/assignments");
    const ul = document.getElementById("assignment-list");
    ul.innerHTML = list.map((a) => `<li>${escapeHtml(a.original_name)}</li>`).join("");
  }

  document.getElementById("btn-upload").onclick = async () => {
    const input = document.getElementById("file-input");
    if (!input.files.length) return;
    for (const file of input.files) {
      const fd = new FormData();
      fd.append("file", file);
      if (!(await ensureLoggedIn())) return;
      await apiFetch("/assignment", { method: "POST", body: fd });
    }
    input.value = "";
    loadAssignments();
  };
  loadAssignments();

  // ---------- AI 教练 ----------
  document.getElementById("btn-coach").onclick = async () => {
    const box = document.getElementById("coach-content");
    box.textContent = "";
    box.classList.add("review-loading");
    try {
      if (!(await ensureLoggedIn())) return;
      const data = await apiJson("/coach", { method: "POST" });
      box.textContent = data.advice || "暂无建议";
    } catch (e) {
      box.textContent = "获取失败，请稍后重试";
    } finally {
      box.classList.remove("review-loading");
    }
  };

  // ---------- AI Agent ----------
  const agentOutput = document.getElementById("agent-output");

  function setAgentOutput(text) {
    if (agentOutput) agentOutput.textContent = text || "";
  }

  const agentPlanBtn = document.getElementById("btn-agent-plan");
  if (agentPlanBtn) {
    agentPlanBtn.onclick = async () => {
      if (!(await ensureLoggedIn())) return;
      const goal = (document.getElementById("agent-goal")?.value || "").trim();
      if (!goal) return;
      const data = await apiJson("/agent/auto_plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal, days: 7 }),
      });
      setAgentOutput(`已自动规划 ${data.count || 0} 个任务：\n${(data.tasks || []).join("\n")}`);
      loadTasks();
      loadEfficiencyPanel();
    };
  }

  const agentReminderBtn = document.getElementById("btn-agent-reminders");
  if (agentReminderBtn) {
    agentReminderBtn.onclick = async () => {
      if (!(await ensureLoggedIn())) return;
      const data = await apiJson("/agent/reminders");
      setAgentOutput((data.items || []).join("\n") || "暂无提醒");
    };
  }

  const agentSummaryBtn = document.getElementById("btn-agent-summary");
  if (agentSummaryBtn) {
    agentSummaryBtn.onclick = async () => {
      if (!(await ensureLoggedIn())) return;
      const data = await apiJson("/agent/auto_summary", { method: "POST" });
      setAgentOutput(`总结：${data.summary || "暂无"}\n\n下一步：${data.next_step || "保持节奏"}`);
    };
  }

  const agentAdjustBtn = document.getElementById("btn-agent-adjust");
  if (agentAdjustBtn) {
    agentAdjustBtn.onclick = async () => {
      if (!(await ensureLoggedIn())) return;
      const data = await apiJson("/agent/auto_adjust", { method: "POST" });
      setAgentOutput(`已自动调整任务 ${data.adjusted_tasks || 0} 个。\n当前拖延指数：${data.metrics?.procrastination_index ?? 0}`);
      loadTasks();
      loadEfficiencyPanel();
    };
  }

  // ---------- 团队协作 ----------
  let currentGroupId = null;

  async function loadGroups() {
    if (!(await ensureLoggedIn())) return;
    const groups = await apiJson("/groups");
    const select = document.getElementById("group-select");
    if (!select) return;
    if (groups.length === 0) {
      select.innerHTML = "<option value=''>暂无小组</option>";
      currentGroupId = null;
      document.getElementById("group-member-list").innerHTML = "";
      document.getElementById("team-task-list").innerHTML = "";
      return;
    }
    select.innerHTML = groups.map((g) => `<option value="${g.id}">${escapeHtml(g.name)}</option>`).join("");
    if (!currentGroupId || !groups.find((g) => String(g.id) === String(currentGroupId))) {
      currentGroupId = String(groups[0].id);
    }
    select.value = String(currentGroupId);
    await loadGroupMembersAndTasks();
  }

  async function loadGroupMembersAndTasks() {
    if (!currentGroupId) return;
    const [members, tasks] = await Promise.all([apiJson(`/groups/${currentGroupId}/members`), apiJson(`/groups/${currentGroupId}/tasks`)]);
    const memberUl = document.getElementById("group-member-list");
    const taskUl = document.getElementById("team-task-list");
    if (memberUl) {
      memberUl.innerHTML = members.map((m) => `<li>${escapeHtml(m.username)}（${escapeHtml(m.role)}）</li>`).join("");
    }
    if (taskUl) {
      taskUl.innerHTML = tasks
        .map(
          (t) =>
            `<li><label class="task-check"><input type="checkbox" data-team-id="${t.id}" ${t.completed ? "checked" : ""}><span>${escapeHtml(t.title)}${t.assignee_username ? ` @${escapeHtml(t.assignee_username)}` : ""}</span></label></li>`
        )
        .join("");
      taskUl.querySelectorAll("input[data-team-id]").forEach((input) => {
        input.addEventListener("change", async (e) => {
          const id = e.target.getAttribute("data-team-id");
          await apiJson(`/groups/${currentGroupId}/tasks/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ completed: e.target.checked }),
          });
        });
      });
    }
  }

  const groupCreateBtn = document.getElementById("btn-group-create");
  if (groupCreateBtn) {
    groupCreateBtn.onclick = async () => {
      const errorEl = document.getElementById("team-error");
      try {
        if (!(await ensureLoggedIn())) return;
        const name = (document.getElementById("group-name")?.value || "").trim();
        if (!name) return;
        await apiJson("/groups", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name }),
        });
        document.getElementById("group-name").value = "";
        errorEl.textContent = "";
        await loadGroups();
      } catch (e) {
        errorEl.textContent = e.message || "创建失败";
      }
    };
  }

  const groupSelect = document.getElementById("group-select");
  if (groupSelect) {
    groupSelect.onchange = async (e) => {
      currentGroupId = e.target.value || null;
      await loadGroupMembersAndTasks();
    };
  }

  const addMemberBtn = document.getElementById("btn-group-add-member");
  if (addMemberBtn) {
    addMemberBtn.onclick = async () => {
      const errorEl = document.getElementById("team-error");
      try {
        if (!(await ensureLoggedIn()) || !currentGroupId) return;
        const username = (document.getElementById("group-member-username")?.value || "").trim();
        if (!username) return;
        await apiJson(`/groups/${currentGroupId}/members`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username }),
        });
        document.getElementById("group-member-username").value = "";
        errorEl.textContent = "";
        await loadGroupMembersAndTasks();
      } catch (e) {
        errorEl.textContent = e.message || "添加成员失败";
      }
    };
  }

  const createTeamTaskBtn = document.getElementById("btn-team-task-create");
  if (createTeamTaskBtn) {
    createTeamTaskBtn.onclick = async () => {
      const errorEl = document.getElementById("team-error");
      try {
        if (!(await ensureLoggedIn()) || !currentGroupId) return;
        const title = (document.getElementById("team-task-title")?.value || "").trim();
        const assignee_username = (document.getElementById("team-task-assignee")?.value || "").trim();
        if (!title) return;
        await apiJson(`/groups/${currentGroupId}/tasks`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title, assignee_username }),
        });
        document.getElementById("team-task-title").value = "";
        document.getElementById("team-task-assignee").value = "";
        errorEl.textContent = "";
        await loadGroupMembersAndTasks();
      } catch (e) {
        errorEl.textContent = e.message || "创建团队任务失败";
      }
    };
  }

  // ---------- 初始化 ----------
  (async function init() {
    if (!(await ensureLoggedIn())) return;
    loadAll();
  })();

  async function loadAll() {
    await Promise.all([loadTasks(), loadGoals(), loadAssignments(), refreshStats(), loadEfficiencyPanel(), loadGroups()]);
    if (!chartInstance) initChart();
  }
})();
