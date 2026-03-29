import re

with open("templates/bodyweight.html", "r") as f:
    content = f.read()

replacement_html = """                <div class="tab-pane" id="tab-history">
                    <!-- Filters and Controls -->
                    <div class="row mb-3 align-items-center">
                        <div class="col-md-6 mb-2 mb-md-0">
                            <label class="form-label me-2 d-inline-block">Filter by House:</label>
                            <select id="houseFilter" class="form-select d-inline-block w-auto">
                                <option value="all">All Houses</option>
                                {% for f in active_flocks %}
                                    <option value="{{ f.house.name }}">{{ f.house.name }}</option>
                                {% endfor %}
                            </select>
                        </div>
                        <div class="col-md-6 text-md-end">
                            <button class="btn btn-outline-secondary btn-sm" onclick="toggleAllAccordions(true)">Expand All</button>
                            <button class="btn btn-outline-secondary btn-sm ms-2" onclick="toggleAllAccordions(false)">Collapse All</button>
                        </div>
                    </div>

                    <!-- Chart Space (Hidden by Default) -->
                    <div id="chartContainer" class="card mb-4" style="display: none;">
                        <div class="card-header d-flex justify-content-between align-items-center">
                            <h3 class="card-title">Performance Charts</h3>
                            <div class="d-flex gap-2">
                                <select id="chartStartWeek" class="form-select form-select-sm w-auto">
                                    <option value="10">Past 10 Weeks</option>
                                    <option value="20">Past 20 Weeks</option>
                                    <option value="all">All Data</option>
                                </select>
                                <label class="form-check form-switch mt-1 ms-2">
                                    <input class="form-check-input" type="checkbox" id="togglePartitions">
                                    <span class="form-check-label small">Show Partitions</span>
                                </label>
                            </div>
                        </div>
                        <div class="card-body">
                            <div class="row">
                                <div class="col-md-6">
                                    <div id="chart-bw-male" style="min-height: 300px;"></div>
                                </div>
                                <div class="col-md-6">
                                    <div id="chart-bw-female" style="min-height: 300px;"></div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Accordion Log -->
                    <div class="accordion" id="accordionBodyweightLog">
                        {% for log in bodyweight_logs %}
                        <div class="accordion-item bw-log-item" data-house="{{ log.house_name }}">
                            <h2 class="accordion-header" id="heading-{{ log.log_id }}">
                                <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#collapse-{{ log.log_id }}" aria-expanded="false" aria-controls="collapse-{{ log.log_id }}">
                                    <strong>{{ log.house_name }}</strong>&nbsp;- Age: Week {{ log.age_weeks }}&nbsp;<span class="text-muted ms-auto small">{{ log.date.strftime('%Y-%m-%d') }}</span>
                                </button>
                            </h2>
                            <div id="collapse-{{ log.log_id }}" class="accordion-collapse collapse" aria-labelledby="heading-{{ log.log_id }}" data-bs-parent="#accordionBodyweightLog">
                                <div class="accordion-body">
                                    <div class="d-flex justify-content-between align-items-start mb-3">
                                        <div>
                                            <h5 class="mb-1">House Average Variance</h5>
                                            <div class="text-muted small">
                                                Male:
                                                <span class="{% if log.avg_m_var > 0 %}text-success{% elif log.avg_m_var < 0 %}text-danger{% else %}text-muted{% endif %}">
                                                    {{ "%.1f"|format(log.avg_m_var) }}%
                                                </span>
                                                | Female:
                                                <span class="{% if log.avg_f_var > 0 %}text-success{% elif log.avg_f_var < 0 %}text-danger{% else %}text-muted{% endif %}">
                                                    {{ "%.1f"|format(log.avg_f_var) }}%
                                                </span>
                                            </div>
                                        </div>
                                        {% if log.has_report %}
                                        <button class="btn btn-sm btn-outline-primary" data-bs-toggle="modal" data-bs-target="#viewModal_{{ log.house_name | replace(' ', '_') }}_{{ log.age_weeks }}">
                                            View Report
                                        </button>
                                        {% endif %}
                                    </div>

                                    <div class="row">
                                        <!-- Male Section -->
                                        <div class="col-md-12 mb-3">
                                            <strong>Male:</strong> (Std: {{ log.std_m }}g)
                                            <div class="mt-2">
                                                {% if log.m_parts %}
                                                    {% for p in log.m_parts %}
                                                        <span class="badge bg-light text-dark mb-1 d-inline-block px-2 py-1 me-2 border">
                                                            {{ p.name }}: {{ p.bw }}g <span class="text-muted">({{ p.diff_g }})</span>
                                                            {{ "%.1f"|format(p.unif) }}% <span class="text-muted">({{ p.diff_u }})</span>
                                                            | Var: <span class="{% if p.var_pct > 0 %}text-success{% elif p.var_pct < 0 %}text-danger{% else %}text-muted{% endif %}">{{ "%.1f"|format(p.var_pct) }}%</span>
                                                        </span>
                                                    {% endfor %}
                                                {% else %}
                                                    <span class="badge bg-light text-dark mb-1 d-inline-block px-2 py-1 me-2 border">
                                                        Avg: {{ log.avg_m }}g <span class="text-muted">({{ log.avg_m_diff }})</span>
                                                        {{ "%.1f"|format(log.uni_m) }}%
                                                    </span>
                                                {% endif %}
                                            </div>
                                        </div>

                                        <!-- Female Section -->
                                        <div class="col-md-12">
                                            <strong>Female:</strong> (Std: {{ log.std_f }}g)
                                            <div class="mt-2">
                                                {% if log.f_parts %}
                                                    {% for p in log.f_parts %}
                                                        <span class="badge bg-light text-dark mb-1 d-inline-block px-2 py-1 me-2 border">
                                                            {{ p.name }}: {{ p.bw }}g <span class="text-muted">({{ p.diff_g }})</span>
                                                            {{ "%.1f"|format(p.unif) }}% <span class="text-muted">({{ p.diff_u }})</span>
                                                            | Var: <span class="{% if p.var_pct > 0 %}text-success{% elif p.var_pct < 0 %}text-danger{% else %}text-muted{% endif %}">{{ "%.1f"|format(p.var_pct) }}%</span>
                                                        </span>
                                                    {% endfor %}
                                                {% else %}
                                                    <span class="badge bg-light text-dark mb-1 d-inline-block px-2 py-1 me-2 border">
                                                        Avg: {{ log.avg_f }}g <span class="text-muted">({{ log.avg_f_diff }})</span>
                                                        {{ "%.1f"|format(log.uni_f) }}%
                                                    </span>
                                                {% endif %}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        {% else %}
                        <div class="text-center py-4 text-muted">No grading data available.</div>
                        {% endfor %}
                    </div>
                </div>"""

start_marker = """                <div class="tab-pane" id="tab-history">"""
end_marker = """                </div>\n            </div>\n        </div>\n    </div>\n</div>"""

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx != -1 and end_idx != -1:
    new_content = content[:start_idx] + replacement_html + content[end_idx:]
    with open("templates/bodyweight.html", "w") as f:
        f.write(new_content)
    print("Template patched successfully")
else:
    print("Could not find markers in template")
