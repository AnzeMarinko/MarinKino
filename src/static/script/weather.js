const weatherRoot = document.getElementById("weather-root");

if (weatherRoot) {
    const weather = JSON.parse(weatherRoot.dataset.weather || "{}");
    const minutely = weather.minutely_15 || weather.hourly || {};
    const minutelyUnits = weather.minutely_15_units || weather.hourly_units || {};
    const graph = document.getElementById("weatherChart");
    const locationMessage = document.getElementById("weatherLocationMessage");
    const savedLocationsEl = document.getElementById("savedLocations");
    const currentEpochSecondsEl = document.getElementById("weatherCurrentEpochSeconds");
    const savedLocationsCookie = "marinkino_weather_locations";

    const sloveneWeekdays = [
        "nedelja",
        "ponedeljek",
        "torek",
        "sreda",
        "četrtek",
        "petek",
        "sobota",
    ];

    function formatCurrentDateTime() {
        if (!currentEpochSecondsEl) {
            return;
        }
        const now = new Date();
        const dayName = sloveneWeekdays[now.getDay()];
        const date = now.toLocaleDateString("sl-SI", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
        });
        const time = now.toLocaleTimeString("sl-SI", {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: false,
        });
        currentEpochSecondsEl.textContent = `${dayName} · ${date} · ${time}`;
    }

    formatCurrentDateTime();
    setInterval(formatCurrentDateTime, 1000);

    function readSavedLocations() {
        const cookie = document.cookie
            .split("; ")
            .find(value => value.startsWith(`${savedLocationsCookie}=`));
        if (!cookie) {
            return [];
        }
        try {
            const decoded = decodeURIComponent(cookie.split("=").slice(1).join("="));
            const locations = JSON.parse(decoded);
            return Array.isArray(locations)
                ? locations.filter(location => ![
                    "trenutna lokacija",
                    "moja lokacija",
                ].includes(String(location.name || "").toLowerCase()))
                : [];
        } catch (_error) {
            return [];
        }
    }

    function writeSavedLocations(locations) {
        const value = encodeURIComponent(JSON.stringify(locations.slice(0, 8)));
        document.cookie = `${savedLocationsCookie}=${value}; max-age=31536000; path=/; samesite=lax`;
    }

    function saveLocation(location) {
        const locationName = String(location?.name || "").trim();
        if (
            !locationName
            || ["trenutna lokacija", "moja lokacija"].includes(locationName.toLowerCase())
            || !Number.isFinite(Number(location.lat))
            || !Number.isFinite(Number(location.lon))
        ) {
            return;
        }
        const locations = readSavedLocations().filter(saved =>
            saved.name !== locationName
            && (Number(saved.lat) !== Number(location.lat) || Number(saved.lon) !== Number(location.lon))
        );
        locations.unshift({
            name: locationName,
            lat: Number(location.lat),
            lon: Number(location.lon),
        });
        writeSavedLocations(locations);
    }

    function renderSavedLocations() {
        if (!savedLocationsEl) {
            return;
        }
        savedLocationsEl.innerHTML = "";
        const currentLocationButton = document.createElement("button");
        currentLocationButton.id = "weatherLocationButton";
        currentLocationButton.className = "current-location-button";
        currentLocationButton.type = "button";
        currentLocationButton.innerHTML = "<i class='bi bi-crosshair'></i><span>Trenutna lokacija</span>";
        savedLocationsEl.appendChild(currentLocationButton);
        currentLocationButton.addEventListener("click", () => {
            if (!navigator.geolocation) {
                locationMessage.textContent = "Brskalnik ne podpira določanja lokacije.";
                return;
            }
            locationMessage.textContent = "Pridobivam trenutno lokacijo ...";
            navigator.geolocation.getCurrentPosition(position => {
                const params = new URLSearchParams({
                    location: "Trenutna lokacija",
                    lat: position.coords.latitude,
                    lon: position.coords.longitude,
                    refresh: Date.now(),
                });
                window.location.href = `/weather?${params}`;
            }, error => {
                if (error.code === 1) {
                    locationMessage.textContent = "Dostop zavrnjen. Ponastavi dovoljenje za lokacijo pri nastavitvah te strani in klikni znova.";
                    return;
                }
                locationMessage.textContent = "Lokacije ni bilo mogoče določiti. Klikni znova in dovoli dostop.";
            }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
        });
        const locations = readSavedLocations();
        if (!locations.length) {
            const emptyMessage = document.createElement("span");
            emptyMessage.className = "weather-source saved-locations-empty";
            emptyMessage.textContent = "Še nimaš shranjenih lokacij.";
            savedLocationsEl.appendChild(emptyMessage);
            return;
        }
        locations.forEach(location => {
            const link = document.createElement("a");
            link.className = "saved-location";
            link.href = `/weather?location=${encodeURIComponent(location.name)}&lat=${encodeURIComponent(location.lat)}&lon=${encodeURIComponent(location.lon)}`;
            link.innerHTML = `<i class="bi bi-geo-alt"></i><span></span>`;
            link.querySelector("span").textContent = location.name;

            const remove = document.createElement("button");
            remove.className = "saved-location-remove";
            remove.type = "button";
            remove.title = `Izbriši lokacijo ${location.name}`;
            remove.setAttribute("aria-label", `Izbriši lokacijo ${location.name}`);
            remove.innerHTML = "<i class='bi bi-x-lg'></i>";
            remove.addEventListener("click", event => {
                event.preventDefault();
                event.stopPropagation();
                writeSavedLocations(readSavedLocations().filter(saved => saved.name !== location.name));
                renderSavedLocations();
            });
            link.appendChild(remove);
            savedLocationsEl.appendChild(link);
        });
    }

    const forecastToggle = document.querySelector(".weather-more-toggle");
    const extraForecastRow = document.querySelector(".weather-daily-list--extra");
    const hiddenForecastDays = document.querySelectorAll(".weather-day-extra");
    if (forecastToggle && extraForecastRow && hiddenForecastDays.length) {
        forecastToggle.hidden = false;
        forecastToggle.addEventListener("click", () => {
            const isExpanded = forecastToggle.dataset.expanded === "true";
            hiddenForecastDays.forEach(day => {
                day.hidden = isExpanded;
            });
            forecastToggle.dataset.expanded = String(!isExpanded);
            forecastToggle.textContent = isExpanded ? "Več" : "Manj";
            forecastToggle.setAttribute("aria-expanded", String(!isExpanded));
        });
    }

    renderSavedLocations();
    if (Number.isFinite(Number(weather.latitude)) && Number.isFinite(Number(weather.longitude))) {
        saveLocation({
            name: weather.location,
            lat: weather.latitude,
            lon: weather.longitude,
        });
        renderSavedLocations();
    }
    document.querySelectorAll(".location-option").forEach(option => {
        option.addEventListener("click", () => {
            saveLocation({
                name: option.dataset.locationName,
                lat: option.dataset.locationLat,
                lon: option.dataset.locationLon,
            });
        });
    });

    const currentUrl = new URL(window.location.href);
    if (currentUrl.searchParams.has("lat") && currentUrl.searchParams.has("lon")) {
        saveLocation({
            name: currentUrl.searchParams.get("location") || "Moja lokacija",
            lat: currentUrl.searchParams.get("lat"),
            lon: currentUrl.searchParams.get("lon"),
        });
        renderSavedLocations();
    }

    function allAvailableHours(times, values) {
        return times
            .map((time, index) => ({ time, value: values[index] }))
            .filter(point => point.value !== null && point.value !== undefined);
    }

    function addSeries(data, name, color, axis, unit) {
        if (!data.length) {
            return null;
        }
        const unitLabel = unit ? ` ${unit}` : "";
        return {
            x: data.map(point => new Date(point.time)),
            y: data.map(point => point.value),
            mode: "lines",
            name: `${name} (${unit || ""})`,
            line: { color, width: 2.5 },
            yaxis: axis,
            hovertemplate: `${name}: %{y:.1f}${unitLabel}<extra></extra>`,
        };
    }

    const times = minutely.time || [];
    const series = key => allAvailableHours(
        times,
        minutely[key] || [],
    );
    const traces = [
        addSeries(series("temperature_2m"), "Temperatura", "#d9485f", "y", minutelyUnits.temperature_2m),
        addSeries(series("wind_speed_10m"), "Veter", "#1f9d55", "y3", minutelyUnits.wind_speed_10m),
        addSeries(series("global_tilted_irradiance"), "Obsevanje", "#ed9b18", "y4", minutelyUnits.global_tilted_irradiance),
    ];
    const currentTime = new Date();
    const isPhoneChartWindow = window.matchMedia("(max-width: 575.98px)").matches;
    const initialStart = new Date(currentTime);
    const initialEnd = new Date(currentTime.getTime() + (isPhoneChartWindow ? 24 : 48) * 60 * 60 * 1000);
    const timeTicks = [];
    const timeTickLabels = [];
    const compactPhoneXAxis = window.matchMedia("(max-width: 575.98px)").matches;
    times.forEach(time => {
        const date = new Date(time);
        const onNoon = date.getHours() === 12 && date.getMinutes() === 0;
        const onSixHourMark = date.getHours() % 6 === 0 && date.getMinutes() === 0;
        const shouldShowTick = compactPhoneXAxis
            ? onNoon
            : (onNoon || onSixHourMark);
        if (shouldShowTick) {
            const hourLabel = `${String(date.getHours()).padStart(2, "0")}:00`;
            const label = onNoon
                ? `${sloveneWeekdays[date.getDay()]} ${hourLabel} · ${date.getDate()}. ${date.getMonth() + 1}.`
                : hourLabel;
            timeTicks.push(date);
            timeTickLabels.push(label);
        }
    });

    const nightShapes = [];
    const daylight = minutely.is_day || [];
    let nightStart = null;
    times.forEach((time, index) => {
        const isNight = daylight[index] === 0;
        if (isNight && nightStart === null) {
            nightStart = new Date(time);
        }
        const isLastPoint = index === times.length - 1;
        if (nightStart !== null && (!isNight || isLastPoint)) {
            const nightEnd = !isNight ? new Date(time) : new Date(
                new Date(time).getTime() + 15 * 60 * 1000,
            );
            nightShapes.push({
                type: "rect",
                x0: nightStart,
                x1: nightEnd,
                y0: 0,
                y1: 1,
                yref: "paper",
                fillcolor: "rgba(20, 32, 50, 0.08)",
                line: { width: 0 },
                layer: "below",
            });
            nightStart = null;
        }
    });
    const rain = series("precipitation");
    if (rain.length) {
        const hourlyRain = [];
        const hourlyMap = new Map();

        rain.forEach(point => {
            const date = new Date(point.time);
            const hourKey = new Date(date.getFullYear(), date.getMonth(), date.getDate(), date.getHours()).toISOString();
            if (!hourlyMap.has(hourKey)) {
                hourlyMap.set(hourKey, { time: hourKey, value: 0 });
            }
            hourlyMap.get(hourKey).value += Number(point.value || 0);
        });

        hourlyRain.push(...Array.from(hourlyMap.values()).sort((a, b) => new Date(a.time) - new Date(b.time)));

        traces.push({
            x: hourlyRain.map(point => new Date(point.time)),
            y: hourlyRain.map(point => point.value),
            type: "bar",
            name: `Padavine (${minutelyUnits.precipitation || "mm"})`,
            marker: { color: "#4285bd", opacity: 0.7 },
            yaxis: "y2",
            hovertemplate: `Padavine: %{y:.1f} mm<extra></extra>`,
        });
    }

    if (graph && traces.some(Boolean)) {
        Plotly.newPlot(graph, traces.filter(Boolean), {
            margin: { t: 24, r: 18, b: 54, l: 42 },
            dragmode: "pan",
            hovermode: "x unified",
            hoverlabel: {
                namelength: -1,
            },
            spikedistance: -1,
            legend: {
                orientation: "h",
                x: 0,
                xanchor: "left",
                y: 1.12,
                yanchor: "bottom",
                bgcolor: "rgba(255,255,255,0.6)",
                bordercolor: "rgba(140,160,185,0.25)",
                borderwidth: 1,
            },
            xaxis: {
                type: "date",
                title: "Čas",
                range: [initialStart, initialEnd],
                gridcolor: "rgba(80, 110, 140, .08)",
                showspikes: true,
                showgrid: true,
                showline: true,
                fixedrange: false,
                tickmode: "array",
                tickvals: timeTicks,
                ticktext: timeTickLabels,
                tickangle: compactPhoneXAxis ? 0 : "auto",
            },
            yaxis: { title: "°C", side: "left", position: 0.0, tickfont: { color: "#d9485f" }, showspikes: true, showline: true, showgrid: false, fixedrange: true },
            yaxis2: { title: "mm", overlaying: "y", side: "right", position: 1.0, tickfont: { color: "#4285bd" }, showspikes: true, showline: true, showgrid: false, fixedrange: true },
            yaxis3: { overlaying: "y", side: "right", position: 0.98, showline: false, showticklabels: false, showgrid: false, zeroline: false, fixedrange: true },
            yaxis4: { overlaying: "y", side: "right", position: 1.02, showline: false, showticklabels: false, showgrid: false, zeroline: false, fixedrange: true },
            shapes: [...nightShapes, {
                type: "line",
                x0: currentTime,
                x1: currentTime,
                y0: 0,
                y1: 1,
                yref: "paper",
                line: { color: "#d39e00", width: 4, dash: "dash" },
            }],
            annotations: [{
                x: currentTime,
                y: 1.02,
                yref: "paper",
                text: "Zdaj",
                showarrow: false,
                yshift: 12,
                font: { color: "#d39e00", size: 12, weight: "bold" },
            }],
            autosize: true,
        }, {
            responsive: true,
            showspikes: true,
            displayModeBar: true,
            displaylogo: false,
            modeBarButtonsToRemove: [
                'toImage', 'pan2d', 'zoom2d', 'select2d', 'lasso2d', 'zoomIn2d', 'zoomOut2d', 'autoScale2d', 'hoverClosestCartesian', 'hoverCompareCartesian', 'toggleSpikelines',
            ],
        });

        window.addEventListener("resize", () => {
            if (graph) {
                Plotly.Plots.resize(graph);
            }
        });
    }

}
