// --- toggleTheme ---
function toggleTheme() {
            const isDark = document.documentElement.classList.toggle('dark');
            const themeIcon = document.getElementById('theme-toggle-icon');
            if (isDark) {
                localStorage.setItem('theme', 'dark');
                themeIcon.className = 'fa-solid fa-sun text-yellow-400';
                showToast("Modo Oscuro activado");
            } else {
                localStorage.setItem('theme', 'light');
                themeIcon.className = 'fa-solid fa-moon text-slate-700';
                showToast("Modo Claro activado");
            }
        }

// --- switchTab ---
function switchTab(tabId) {
            document.querySelectorAll('.tab-content').forEach(tab => tab.classList.add('hidden'));
            document.querySelectorAll('.nav-btn').forEach(btn => {
                btn.classList.remove('active', 'bg-indigo-600/10', 'dark:bg-indigo-600/15', 'text-indigo-600', 'dark:text-indigo-400', 'border-l-4', 'border-indigo-500');
                btn.classList.add('text-slate-500', 'dark:text-slate-400');
            });

            document.getElementById(`tab-${tabId}`).classList.remove('hidden');
            const activeBtn = document.getElementById(`btn-tab-${tabId}`);
            activeBtn.classList.add('active', 'bg-indigo-600/10', 'dark:bg-indigo-600/15', 'text-indigo-600', 'dark:text-indigo-400', 'border-l-4', 'border-indigo-500');
            activeBtn.classList.remove('text-slate-500', 'dark:text-slate-400');

            if (tabId === 'dashboard') {
                recalculateCombosStock();
                renderDashboard();
            }
            if (tabId === 'catalogo') {
                renderProducts();
            }
            if (tabId === 'ventas') {
                populateVentasSelects();
            }
            if (tabId === 'articulos') {
                renderCrudProducts();
            }
            if (tabId === 'contactos') {
                renderContacts();
            }
        }

// --- updateRates ---
function updateRates() {
            const bcvVal = parseFloat(document.getElementById('input-bcv').value);
            const factorVal = parseFloat(document.getElementById('input-factor').value);

            if (!isNaN(bcvVal) && !isNaN(factorVal)) {
                const isDiff = (globalBCV !== bcvVal) || (globalFactor !== factorVal);
                globalBCV = bcvVal;
                globalFactor = factorVal;

                const adjustedRate = globalBCV * globalFactor;

                document.getElementById('header-bcv-display').innerText = `${globalBCV.toFixed(2)} Bs`;
                document.getElementById('header-factor-display').innerText = `${globalFactor.toFixed(2)}x`;
                document.getElementById('header-adjusted-display').innerText = `${adjustedRate.toFixed(2)} Bs`;

                if (isDiff) {
                    const now = new Date();
                    const nowStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
                    ratesAuditLog.unshift({
                        datetime: nowStr,
                        bcv: globalBCV,
                        factor: globalFactor,
                        adjusted: adjustedRate,
                        user: "Operador Principal"
                    });
                    renderRatesAudit();
                }

                renderProducts();
                updateCrossSellingOutput();
                recalculateNoteTotal();
            }
        }

// --- simulateSync ---
function simulateSync() {
            showToast("Sincronizando con Binance & DolarAPI (BCV)...");
            setTimeout(() => {
                document.getElementById('input-bcv').value = "60.45";
                document.getElementById('input-factor').value = "1.39";
                updateRates();
                document.getElementById('sync-time-lbl').innerText = "Hace un momento";
                showToast("Sincronización exitosa!");
            }, 1200);
        }

