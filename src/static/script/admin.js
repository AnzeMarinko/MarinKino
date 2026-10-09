(() => {
    const root = document.querySelector(".admin-page");
    if (!root) return;
    root.querySelectorAll("form[data-confirm-delete]").forEach(form => {
        form.addEventListener("submit", event => {
            if (!window.confirm(`Izbrišem objavo »${form.dataset.confirmDelete}«? Izbrisa ni mogoče razveljaviti.`)) event.preventDefault();
        });
    });
    root.querySelectorAll("table[data-sortable]").forEach(table => {
        table.querySelectorAll("thead th[data-sort]").forEach((heading, index) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "admin-sort-button";
            button.textContent = heading.textContent.trim();
            heading.replaceChildren(button);
            heading.setAttribute("aria-sort", "none");
            button.addEventListener("click", () => {
                const ascending = heading.getAttribute("aria-sort") !== "ascending";
                table.querySelectorAll("thead th").forEach(other => other.setAttribute("aria-sort", "none"));
                heading.setAttribute("aria-sort", ascending ? "ascending" : "descending");
                const rows = [...table.tBodies[0].rows];
                rows.sort((a, b) => {
                    const value = row => row.cells[index]?.dataset.sortValue ?? row.cells[index]?.textContent.trim() ?? "";
                    const av = value(a), bv = value(b);
                    const numeric = value => {
                        const duration = value.match(/^(\d+)h\s*(\d+)m$/);
                        return duration ? Number(duration[1]) * 60 + Number(duration[2]) : parseFloat(value.replace(',', '.')) || 0;
                    };
                    const result = heading.dataset.sort === "number" ? numeric(av) - numeric(bv) : av.localeCompare(bv, "sl", { numeric: true, sensitivity: "base" });
                    return ascending ? result : -result;
                });
                rows.forEach(row => table.tBodies[0].appendChild(row));
            });
        });
    });
    root.querySelectorAll("[data-table-search]").forEach(input => {
        const table = document.getElementById(input.dataset.tableSearch);
        const statusFilter = root.querySelector(`[data-table-status="${table.id}"]`);
        const notice = root.querySelector(`[data-table-empty="${table.id}"]`);
        const counter = root.querySelector(`[data-table-count="${table.id}"]`);
        function filter() {
            const query = input.value.trim().toLocaleLowerCase("sl");
            let visible = 0;
            [...table.tBodies[0].rows].forEach(row => {
                row.hidden = !row.textContent.toLocaleLowerCase("sl").includes(query) || (statusFilter && statusFilter.value && row.dataset.status !== statusFilter.value);
                if (!row.hidden) visible++;
            });
            if (notice) notice.hidden = visible !== 0;
            if (counter) counter.textContent = `${visible} od ${table.tBodies[0].rows.length}`;
        }
        input.addEventListener("input", filter);
        statusFilter?.addEventListener("change", filter);
        filter();
    });
})();
