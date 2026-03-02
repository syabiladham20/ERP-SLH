import re

def fix_hatch_chart(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # Let's inspect options specifically to see if we messed up any brackets
    # And check the toggle button logic
    # Make sure we didn't remove the datalabels object completely from options plugins

    # 1. Update updateChartTitle function
    new_title_func = """function updateChartTitle(elementId, baseTitle, dataObj, isDaily) {
      const titleEl = document.getElementById(elementId);
      if (!titleEl) return;

      let startAge = '?', endAge = '?';
      let startDate = '', endDate = '';

      if (dataObj && dataObj.dates && dataObj.dates.length > 0) {
          const count = dataObj.dates.length;
          startDate = dataObj.dates[0];
          endDate = dataObj.dates[count - 1];

          if (!isDaily) {
               startAge = startDate;
               endAge = endDate;
          } else {
               if (dataObj.ages && dataObj.ages.length > 0) {
                   startAge = "W" + dataObj.ages[0].split('.')[0];
                   endAge = "W" + dataObj.ages[dataObj.ages.length - 1].split('.')[0];
               } else {
                   startAge = "W" + calculateAgeWeeks(new Date(startDate));
                   endAge = "W" + calculateAgeWeeks(new Date(endDate));
               }
          }
      }

      function formatToDDMMYY(dateStr) {
          if (!dateStr || !dateStr.includes('-')) return dateStr;
          const parts = dateStr.split('-');
          if (parts.length === 3) {
             return `${parts[2]}-${parts[1]}-${parts[0].slice(2)}`;
          }
          return dateStr;
      }

      let dynamicText = `${baseTitle} - [${flockHouseName}`;
      if (startAge !== '?' && endAge !== '?') {
          dynamicText += ` (${startAge} to ${endAge}`;
          if (isDaily && startDate && endDate) {
              dynamicText += ` - ${formatToDDMMYY(startDate)} to ${formatToDDMMYY(endDate)}`;
          }
          dynamicText += `)]`;
      } else {
          dynamicText += `]`;
      }

      titleEl.innerText = dynamicText;
  }"""

    # Replace the updateChartTitle function
    content = re.sub(r'function updateChartTitle\((chartTitleId|elementId), baseTitle, dataObj, isDaily\) \{.*?(?=function toggleFullScreenWrapper)', new_title_func + '\n\n  ', content, flags=re.DOTALL)


    with open(filepath, 'w') as f:
        f.write(content)

fix_hatch_chart('templates/flock_detail.html')
fix_hatch_chart('templates/flock_detail_readonly.html')
print("Done titles and formats.")
