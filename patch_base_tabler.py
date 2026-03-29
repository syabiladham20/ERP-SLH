with open('templates/base_tabler.html', 'r') as f:
    content = f.read()

content = content.replace("{% elif item.key == 'nav_weight_grading' %}\n                                    <a class=\"dropdown-item\" href=\"{{ url_for('weight_grading') }}\">{{ item.label }}</a>", "")
content = content.replace("{% elif item.key == 'nav_weight_grading' %}\n                            <li class=\"nav-item role-restricted\" data-allowed-roles=\"Farm,Management\"><a class=\"nav-link\" href=\"{{ url_for('weight_grading') }}\"><span class=\"nav-link-title\">{{ item.label }}</span></a></li>", "")

# Add to health dropdown block 1
target1 = "{% elif h_item.key == 'nav_health_notes' %}\n                                                    <a href=\"{{ url_for('post_mortem') }}\" class=\"dropdown-item\">{{ h_item.label }}</a>"
replace1 = target1 + "\n                                                {% elif h_item.key == 'nav_weight_grading' %}\n                                                    <a href=\"{{ url_for('weight_grading') }}\" class=\"dropdown-item\">{{ h_item.label }}</a>"
content = content.replace(target1, replace1)

# Add to health dropdown block 2
target2 = "{% elif h_item.key == 'nav_health_notes' %}\n                                            <a href=\"{{ url_for('post_mortem') }}\" class=\"dropdown-item\">{{ h_item.label }}</a>"
replace2 = target2 + "\n                                        {% elif h_item.key == 'nav_weight_grading' %}\n                                            <a href=\"{{ url_for('weight_grading') }}\" class=\"dropdown-item\">{{ h_item.label }}</a>"
content = content.replace(target2, replace2)

with open('templates/base_tabler.html', 'w') as f:
    f.write(content)
