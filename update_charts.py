import re

def configure_datalabels(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # We need to make sure datalabels plugin in Hatching Egg chart shows datalabels for bars as well.
    # Replace the datalabels: { display: function... } block in hatchingEggChart.
    hatching_egg_dl = """                  datalabels: {
                       display: function(context) { return context.chart.options.plugins.datalabels.display; },
                       formatter: function(value, context) { if (!value) return ''; return parseFloat(value).toFixed(2) + '%'; }
                  },"""
    content = re.sub(
        r"datalabels: \{\s*display: function\(context\) \{ return context.dataset.type === 'line'; \},\s*formatter: function\(value, context\) \{ if \(!value\) return ''; return parseFloat\(value\).toFixed\(2\) \+ '%'; \}\s*\},",
        hatching_egg_dl,
        content
    )

    with open(filepath, 'w') as f:
        f.write(content)

configure_datalabels('templates/flock_detail.html')
configure_datalabels('templates/flock_detail_readonly.html')


def configure_fertility(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # For Fertility (stacked bar in read_only), we need datalabels align center.
    fertility_repl = """                  {
                      label: 'Fertile %',
                      data: dFertile,
                      backgroundColor: 'rgba(75, 192, 192, 0.7)',
                      yAxisID: 'y',
                      datalabels: { align: 'center', anchor: 'center' }
                  },"""
    content = re.sub(
        r"\{\s*label: 'Fertile %',\s*data: dFertile,\s*backgroundColor: 'rgba\(75, 192, 192, 0\.7\)',\s*yAxisID: 'y'\s*\},",
        fertility_repl,
        content
    )

    # Do the same for Clear % and Rotten % (stacked components)
    clear_repl = """                  {
                      label: 'Clear %',
                      data: dClear,
                      backgroundColor: 'rgba(255, 206, 86, 0.7)',
                      yAxisID: 'y',
                      datalabels: { align: 'center', anchor: 'center' }
                  },"""
    content = re.sub(
        r"\{\s*label: 'Clear %',\s*data: dClear,\s*backgroundColor: 'rgba\(255, 206, 86, 0\.7\)',\s*yAxisID: 'y'\s*\},",
        clear_repl,
        content
    )

    rotten_repl = """                  {
                      label: 'Rotten %',
                      data: dRotten,
                      backgroundColor: 'rgba(255, 99, 132, 0.7)',
                      yAxisID: 'y',
                      datalabels: { align: 'center', anchor: 'center' }
                  },"""
    content = re.sub(
        r"\{\s*label: 'Rotten %',\s*data: dRotten,\s*backgroundColor: 'rgba\(255, 99, 132, 0\.7\)',\s*yAxisID: 'y'\s*\},",
        rotten_repl,
        content
    )

    with open(filepath, 'w') as f:
        f.write(content)

configure_fertility('templates/flock_detail_readonly.html')
