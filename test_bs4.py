from bs4 import BeautifulSoup

html = """
<div class="col-12 col-md-6 mb-2">
  <label class="form-label">Mortality Male (Prod)</label>
  <input type="number" class="form-control" name="mortality_male" value="{{ log.mortality_male if log else 0 }}">
</div>
{% if test %}
  <div>Hello</div>
{% endif %}
"""

soup = BeautifulSoup(html, 'html.parser')
print(str(soup))
