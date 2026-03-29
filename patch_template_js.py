import re

with open("templates/bodyweight.html", "r") as f:
    content = f.read()

js_addition = """
<script src="https://cdn.jsdelivr.net/npm/apexcharts"></script>
<script>
    // Toggle all accordions
    function toggleAllAccordions(expand) {
        const accordionBodies = document.querySelectorAll('#accordionBodyweightLog .accordion-collapse');
        const accordionButtons = document.querySelectorAll('#accordionBodyweightLog .accordion-button');

        accordionBodies.forEach(body => {
            if (expand) {
                body.classList.add('show');
            } else {
                body.classList.remove('show');
            }
        });

        accordionButtons.forEach(btn => {
            if (expand) {
                btn.classList.remove('collapsed');
                btn.setAttribute('aria-expanded', 'true');
            } else {
                btn.classList.add('collapsed');
                btn.setAttribute('aria-expanded', 'false');
            }
        });
    }

    // Charting logic
    document.addEventListener("DOMContentLoaded", function() {
        const houseFilter = document.getElementById('houseFilter');
        const chartContainer = document.getElementById('chartContainer');
        const togglePartitions = document.getElementById('togglePartitions');
        const chartStartWeek = document.getElementById('chartStartWeek');
        const accordionItems = document.querySelectorAll('.bw-log-item');

        let maleChart = null;
        let femaleChart = null;

        // Pass the log data from python to JS
        const logData = {{ bodyweight_logs | tojson | safe }};

        function renderCharts(selectedHouse) {
            // Filter logs by house
            let filteredLogs = logData.filter(log => log.house_name === selectedHouse);

            // Sort by age week ascending for charts
            filteredLogs.sort((a, b) => a.age_weeks - b.age_weeks);

            // Limit by start week selection
            const numWeeks = chartStartWeek.value;
            if (numWeeks !== 'all') {
                const limit = parseInt(numWeeks);
                filteredLogs = filteredLogs.slice(-limit);
            }

            const categories = filteredLogs.map(log => 'Week ' + log.age_weeks);
            const showPartitions = togglePartitions.checked;

            // Generate Series for Male
            let maleSeries = [];
            let femaleSeries = [];

            if (!showPartitions) {
                // Averages only
                maleSeries.push({
                    name: 'Male Average',
                    data: filteredLogs.map(log => log.avg_m || null)
                });

                femaleSeries.push({
                    name: 'Female Average',
                    data: filteredLogs.map(log => log.avg_f || null)
                });
            } else {
                // Partitions for Male
                let maxMParts = 0;
                filteredLogs.forEach(log => {
                    if (log.m_parts && log.m_parts.length > maxMParts) {
                        maxMParts = log.m_parts.length;
                    }
                });

                if (maxMParts > 0) {
                    for (let i = 0; i < maxMParts; i++) {
                        maleSeries.push({
                            name: `P${i+1}`,
                            data: filteredLogs.map(log => {
                                if (log.m_parts && log.m_parts[i]) {
                                    return log.m_parts[i].bw;
                                }
                                return log.avg_m || null; // fallback to avg if merged
                            })
                        });
                    }
                } else {
                    maleSeries.push({
                        name: 'Male Average',
                        data: filteredLogs.map(log => log.avg_m || null)
                    });
                }

                // Partitions for Female
                let maxFParts = 0;
                filteredLogs.forEach(log => {
                    if (log.f_parts && log.f_parts.length > maxFParts) {
                        maxFParts = log.f_parts.length;
                    }
                });

                if (maxFParts > 0) {
                    for (let i = 0; i < maxFParts; i++) {
                        femaleSeries.push({
                            name: `P${i+1}`,
                            data: filteredLogs.map(log => {
                                if (log.f_parts && log.f_parts[i]) {
                                    return log.f_parts[i].bw;
                                }
                                return log.avg_f || null;
                            })
                        });
                    }
                } else {
                    femaleSeries.push({
                        name: 'Female Average',
                        data: filteredLogs.map(log => log.avg_f || null)
                    });
                }
            }

            // Common Options
            const getChartOptions = (series, title, yTitle) => {
                return {
                    series: series,
                    chart: {
                        type: 'line',
                        height: 350,
                        toolbar: { show: true }
                    },
                    dataLabels: {
                        enabled: true,
                        formatter: function (val, opts) {
                            if (opts.dataPointIndex === 0) return val;
                            const prevVal = opts.w.globals.series[opts.seriesIndex][opts.dataPointIndex - 1];
                            if (prevVal && val) {
                                const diff = val - prevVal;
                                return `${val} (+${diff.toFixed(0)})`;
                            }
                            return val;
                        },
                        style: {
                            fontSize: '10px'
                        },
                        background: { enabled: false }
                    },
                    stroke: { curve: 'straight', width: 2 },
                    title: { text: title, align: 'left' },
                    xaxis: { categories: categories },
                    yaxis: { title: { text: yTitle } },
                    markers: { size: 4 },
                    tooltip: {
                        y: { formatter: function (val) { return val + "g"; } }
                    }
                };
            };

            // Male Chart
            if (maleChart) {
                maleChart.destroy();
            }
            maleChart = new ApexCharts(document.querySelector("#chart-bw-male"), getChartOptions(maleSeries, 'Male Bodyweight', 'Grams'));
            maleChart.render();

            // Female Chart
            if (femaleChart) {
                femaleChart.destroy();
            }
            femaleChart = new ApexCharts(document.querySelector("#chart-bw-female"), getChartOptions(femaleSeries, 'Female Bodyweight', 'Grams'));
            femaleChart.render();
        }

        // Filtering Logic
        houseFilter.addEventListener('change', function() {
            const selectedHouse = this.value;

            if (selectedHouse === 'all') {
                chartContainer.style.display = 'none';
                accordionItems.forEach(item => item.style.display = 'block');
            } else {
                chartContainer.style.display = 'block';
                accordionItems.forEach(item => {
                    if (item.getAttribute('data-house') === selectedHouse) {
                        item.style.display = 'block';
                    } else {
                        item.style.display = 'none';
                    }
                });
                renderCharts(selectedHouse);
            }
        });

        // Trigger chart updates
        togglePartitions.addEventListener('change', function() {
            if (houseFilter.value !== 'all') renderCharts(houseFilter.value);
        });

        chartStartWeek.addEventListener('change', function() {
            if (houseFilter.value !== 'all') renderCharts(houseFilter.value);
        });
    });
</script>
"""

# Append before final endblock
idx = content.rfind("{% endblock %}")
if idx != -1:
    new_content = content[:idx] + js_addition + "\n" + content[idx:]
    with open("templates/bodyweight.html", "w") as f:
        f.write(new_content)
    print("JS added to template successfully")
else:
    print("Could not find endblock")
