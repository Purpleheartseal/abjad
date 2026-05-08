function getCsrfToken(form) {
    const input = form.querySelector("input[name='csrfmiddlewaretoken']");
    return input ? input.value : "";
}

function getGlobalCsrfToken() {
    const input = document.querySelector("input[name='csrfmiddlewaretoken']");
    if (input) return input.value;
    const cookie = document.cookie
        .split(";")
        .map((item) => item.trim())
        .find((item) => item.startsWith("csrftoken="));
    return cookie ? cookie.split("=")[1] : "";
}

function toggleModal(id, show) {
    const modal = document.getElementById(id);
    if (!modal) return;
    modal.classList.toggle("hidden", !show);
}

document.querySelectorAll("[data-open-modal]").forEach((button) => {
    button.addEventListener("click", () => toggleModal(button.dataset.openModal, true));
});

document.querySelectorAll("[data-close-modal]").forEach((button) => {
    button.addEventListener("click", () => toggleModal(button.dataset.closeModal, false));
});

document.querySelectorAll("[data-toggle-columns]").forEach((button) => {
    button.addEventListener("click", () => {
        const panel = document.getElementById(button.dataset.toggleColumns);
        if (!panel) return;
        panel.classList.toggle("hidden");
    });
});

const calcForm = document.getElementById("calc-form");
if (calcForm) {
    const resultNode = document.getElementById("calc-result");
    const addForm = document.getElementById("add-entry-form");
    const phraseHidden = document.getElementById("phrase-hidden");
    calcForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const formData = new FormData(calcForm);
        const response = await fetch(calcForm.dataset.calcUrl, {
            method: "POST",
            headers: { "X-CSRFToken": getCsrfToken(calcForm) },
            body: formData,
        });
        const payload = await response.json();
        if (!payload.ok) return;
        const labels = {
            phrase: "عبارت",
            normalized_phrase: "عبارت نرمال شده",
            abjad_value: "عدد ابجد",
            prime_index: "چندمین عدد اول",
            digit_root: "ریشه عدد",
            abjad_sum: "مجموع عدد ابجد",
            parity_label: "زوج یا فرد",
            parity_order: "چندمین زوج فرد",
            letter_count: "تعداد حروف",
            dot_count: "تعداد نقطه",
            pronounced_value: "عدد ملفوظی",
            alif_count: "تعداد الف",
            abjad_saghir: "ابجد صغیر",
            breakdown: "تبدیل حرف به عدد",
        };
        resultNode.innerHTML = Object.entries(payload.result)
            .map(([key, value]) => `<div class="preview-item"><strong>${labels[key] || key}</strong><span>${value}</span></div>`)
            .join("");
        resultNode.classList.remove("hidden");
        phraseHidden.value = formData.get("phrase");
        addForm.classList.remove("hidden");
    });
}

const quickCalcForm = document.getElementById("quick-calc-form");
if (quickCalcForm) {
    const quickPhraseInput = document.getElementById("quick-phrase-input");
    const quickAbjadValue = document.getElementById("quick-abjad-value");
    const quickAddButton = document.getElementById("quick-add-button");
    const quickAddHiddenPhrase = document.getElementById("quick-add-hidden-phrase");
    const quickAddSubmitForm = document.getElementById("quick-add-submit-form");

    quickCalcForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const formData = new FormData();
        formData.append("phrase", quickPhraseInput.value);
        const response = await fetch(quickCalcForm.dataset.calcUrl, {
            method: "POST",
            headers: { "X-CSRFToken": getGlobalCsrfToken() },
            body: formData,
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
            quickAbjadValue.textContent = "-";
            quickAddButton.disabled = true;
            return;
        }
        quickAbjadValue.textContent = payload.result.abjad_value;
        quickAddHiddenPhrase.value = quickPhraseInput.value;
        quickAddButton.disabled = !quickPhraseInput.value.trim();
    });

    quickPhraseInput.addEventListener("input", () => {
        quickAbjadValue.textContent = "-";
        quickAddHiddenPhrase.value = "";
        quickAddButton.disabled = true;
    });

    quickAddButton.addEventListener("click", () => {
        if (!quickAddHiddenPhrase.value.trim()) return;
        quickAddSubmitForm.submit();
    });
}

document.querySelectorAll('select[name="source_type"]').forEach((select) => {
    select.addEventListener("change", () => {
        const form = select.closest("form");
        const projectSelect = form?.querySelector('select[name="project"]');
        if (projectSelect) {
            projectSelect.disabled = select.value === "main";
        }
    });
});

const selectAllProjectRows = document.getElementById("select-all-project-rows");
if (selectAllProjectRows) {
    selectAllProjectRows.addEventListener("change", () => {
        document.querySelectorAll(".project-row-check").forEach((checkbox) => {
            checkbox.checked = selectAllProjectRows.checked;
        });
    });
}

const selectAllProjectFiltered = document.getElementById("select-all-project-filtered");
if (selectAllProjectFiltered) {
    selectAllProjectFiltered.addEventListener("change", () => {
        document.querySelectorAll(".project-row-check").forEach((checkbox) => {
            checkbox.checked = selectAllProjectFiltered.checked;
        });
        if (selectAllProjectRows) {
            selectAllProjectRows.checked = selectAllProjectFiltered.checked;
        }
    });
}

const selectAllMainRows = document.getElementById("select-all-main-rows");
if (selectAllMainRows) {
    selectAllMainRows.addEventListener("change", () => {
        document.querySelectorAll(".main-row-check").forEach((checkbox) => {
            checkbox.checked = selectAllMainRows.checked;
        });
    });
}

const selectAllMainFiltered = document.getElementById("select-all-main-filtered");
if (selectAllMainFiltered) {
    selectAllMainFiltered.addEventListener("change", () => {
        document.querySelectorAll(".main-row-check").forEach((checkbox) => {
            checkbox.checked = selectAllMainFiltered.checked;
        });
        if (selectAllMainRows) {
            selectAllMainRows.checked = selectAllMainFiltered.checked;
        }
    });
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function renderCellValue(cell, value) {
    const text = cell.querySelector(".cell-text") || document.createElement("span");
    text.className = "cell-text";
    text.innerHTML = escapeHtml(value);
    cell.innerHTML = "";
    cell.appendChild(text);
}

function applyMismatchState(row, payloadRow) {
    const mismatchFields = payloadRow.mismatch_fields || [];
    row.classList.toggle("mismatch-row", Boolean(payloadRow.has_mismatch));
    row.querySelectorAll("[data-field]").forEach((cell) => {
        cell.classList.toggle("mismatch-cell", mismatchFields.includes(cell.dataset.field));
        if (cell.dataset.field === "phrase") {
            if (mismatchFields.includes("phrase")) {
                cell.title = "این عبارت دارای کاراکتر نامعتبر یا مغایرت محاسباتی است.";
            } else {
                cell.removeAttribute("title");
            }
        }
    });
}

function showCellError(cell, message) {
    const existing = cell.querySelector(".cell-error");
    if (existing) existing.remove();
    const error = document.createElement("div");
    error.className = "cell-error";
    error.textContent = message;
    cell.appendChild(error);
}

function clearCellError(cell) {
    const existing = cell.querySelector(".cell-error");
    if (existing) existing.remove();
}

async function saveInlineCell(cell, editor, originalValue) {
    const row = cell.closest("[data-inline-row]");
    const value = editor.value;
    const formData = new FormData();
    formData.append("field", cell.dataset.field);
    formData.append("value", value);
    try {
        const response = await fetch(row.dataset.updateUrl, {
            method: "POST",
            headers: { "X-CSRFToken": getGlobalCsrfToken() },
            body: formData,
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
            showCellError(cell, payload.error || "ذخیره انجام نشد.");
            return false;
        }
        Object.entries(payload.row).forEach(([field, fieldValue]) => {
            const target = row.querySelector(`[data-field="${field}"]`);
            if (target) renderCellValue(target, fieldValue);
        });
        applyMismatchState(row, payload.row);
        return true;
    } catch (error) {
        showCellError(cell, "ارتباط با سرور برقرار نشد.");
        renderCellValue(cell, originalValue);
        return false;
    }
}

document.querySelectorAll(".inline-edit-table td[data-editable='true']").forEach((cell) => {
    cell.addEventListener("dblclick", () => {
        if (cell.classList.contains("is-editing")) return;
        clearCellError(cell);
        cell.classList.add("is-editing");
        const currentValue = (cell.querySelector(".cell-text")?.textContent || "").trim();
        const isLongText = ["phrase", "breakdown"].includes(cell.dataset.field);
        const editor = document.createElement(isLongText ? "textarea" : "input");
        if (editor.tagName === "INPUT") {
            editor.type = cell.dataset.inputType || "text";
            editor.className = "inline-edit-input";
        } else {
            editor.className = "inline-edit-textarea";
        }
        editor.value = currentValue;
        cell.innerHTML = "";
        cell.appendChild(editor);
        editor.focus();
        editor.select?.();

        let saved = false;
        const finish = async (commit) => {
            if (saved) return;
            saved = true;
            cell.classList.remove("is-editing");
            if (!commit) {
                renderCellValue(cell, currentValue);
                return;
            }
            const ok = await saveInlineCell(cell, editor, currentValue);
            if (!ok) {
                saved = false;
                cell.classList.add("is-editing");
            }
        };

        editor.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                event.preventDefault();
                finish(false);
            }
            if (event.key === "Enter" && (!isLongText || event.ctrlKey || event.metaKey)) {
                event.preventDefault();
                finish(true);
            }
        });

        editor.addEventListener("blur", () => {
            finish(true);
        });
    });
});

function getTableStateKey(table) {
    return `abjad-table-state:${table.dataset.tableId}`;
}

function loadTableState(table) {
    try {
        const raw = localStorage.getItem(getTableStateKey(table));
        return raw ? JSON.parse(raw) : { hidden: [], widths: {} };
    } catch (error) {
        return { hidden: [], widths: {} };
    }
}

function saveTableState(table, state) {
    localStorage.setItem(getTableStateKey(table), JSON.stringify(state));
}

function setColumnVisibility(table, field, visible) {
    table.querySelectorAll(`[data-column="${field}"], [data-field="${field}"]`).forEach((node) => {
        node.dataset.columnHidden = visible ? "false" : "true";
    });
}

function applyTableState(table) {
    const state = loadTableState(table);
    Object.entries(state.widths || {}).forEach(([field, width]) => {
        const col = table.querySelector(`col[data-column="${field}"]`);
        if (col && width) col.style.width = `${width}px`;
    });
    table.querySelectorAll("col[data-column]").forEach((col) => {
        const field = col.dataset.column;
        const visible = !(state.hidden || []).includes(field);
        setColumnVisibility(table, field, visible);
    });
    document.querySelectorAll(`[data-column-toggle="${table.dataset.tableId}"]`).forEach((checkbox) => {
        checkbox.checked = !(state.hidden || []).includes(checkbox.value);
    });
}

function initColumnToggles(table) {
    document.querySelectorAll(`[data-column-toggle="${table.dataset.tableId}"]`).forEach((checkbox) => {
        checkbox.addEventListener("change", () => {
            const state = loadTableState(table);
            const hidden = new Set(state.hidden || []);
            if (checkbox.checked) {
                hidden.delete(checkbox.value);
            } else {
                hidden.add(checkbox.value);
            }
            state.hidden = Array.from(hidden);
            saveTableState(table, state);
            setColumnVisibility(table, checkbox.value, checkbox.checked);
        });
    });
}

function initColumnResize(table) {
    table.querySelectorAll(".col-resizer").forEach((handle) => {
        handle.addEventListener("mousedown", (event) => {
            event.preventDefault();
            event.stopPropagation();
            const field = handle.dataset.resizeColumn;
            const col = table.querySelector(`col[data-column="${field}"]`);
            if (!col) return;
            const startX = event.clientX;
            const startWidth = col.getBoundingClientRect().width;
            handle.classList.add("is-dragging");
            const move = (moveEvent) => {
                const nextWidth = Math.max(90, startWidth + (startX - moveEvent.clientX));
                col.style.width = `${nextWidth}px`;
            };
            const up = () => {
                handle.classList.remove("is-dragging");
                const state = loadTableState(table);
                state.widths = state.widths || {};
                state.widths[field] = Math.round(col.getBoundingClientRect().width);
                saveTableState(table, state);
                window.removeEventListener("mousemove", move);
                window.removeEventListener("mouseup", up);
            };
            window.addEventListener("mousemove", move);
            window.addEventListener("mouseup", up);
        });
    });
}

document.querySelectorAll(".inline-edit-table[data-table-id]").forEach((table) => {
    applyTableState(table);
    initColumnToggles(table);
    initColumnResize(table);
});
