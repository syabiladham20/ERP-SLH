import re

def fix_title_format(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

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

      let dynamicText = `${baseTitle} - ${flockHouseName}`;
      if (startAge !== '?' && endAge !== '?') {
          dynamicText += ` (${startAge} to ${endAge}`;
          if (isDaily && startDate && endDate) {
              dynamicText += ` - ${formatToDDMMYY(startDate)} to ${formatToDDMMYY(endDate)}`;
          }
          dynamicText += `)`;
      }

      titleEl.innerText = dynamicText;
  }"""

    # Check if updateChartTitle exists and replace it exactly.
    # We did this in `fix_hatch_and_common.py` but we wrapped House in [ ]. The user wanted:
    # [Chart Name] - [House (WXX to WXX - dd-mm-yy to dd-mm-yy)]
    # Wait, the prompt says literally:
    # use this format - [Chart Name] - [House (WXX to WXX - dd-mm-yy to dd-mm-yy)]

    new_title_func_literal = """function updateChartTitle(elementId, baseTitle, dataObj, isDaily) {
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
          dynamicText += `)`;
      }
      dynamicText += `]`;

      titleEl.innerText = dynamicText;
  }"""

    content = re.sub(r'function updateChartTitle\((chartTitleId|elementId), baseTitle, dataObj, isDaily\) \{.*?(?=function toggleFullScreenWrapper)', new_title_func_literal + '\n\n  ', content, flags=re.DOTALL)

    with open(filepath, 'w') as f:
        f.write(content)

fix_title_format('templates/flock_detail.html')
fix_title_format('templates/flock_detail_readonly.html')
