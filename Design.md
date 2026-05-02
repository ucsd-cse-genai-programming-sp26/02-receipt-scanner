## Key Design Decisions

### Use of react and sqlite3 to build the app

Though the majority of this code was written by Codex + Claude, it was important for me that I was still able to understnad the code that was written. React and sqlite3 are tools that I have used before, so I chose to use these. 

### Use of GPT 4o Vision as OCR model 

I initially wanted to use Tesseract as the OCR model as it is local, runs on my machine and would not cause me to spend API credits. I decided against this, since I observed the outputs from the Tesseract model were quite poort. 

### Integers for representing USD

I decided to use integers instead of floating point for USD, as this can lead to floating point error. This was a design decision that I had to correct in claude's initial draft of the interface. 

### Using OPENAI model as categorizer rather than string matching 

My initial implementation involved using string matching to determine categories. This ended up being quite terrible and would mark most categories as other, so I switched to using an LLM to make the categories. 


### Don't store raw images

Storing raw images on disk can be quite dangerous and introduce liabilities. I decided to instead extract the text using OCR and only save this, rather than saving these images to disk. 

### Safe Edit / Delete 

I decided to implement the edit / delete item feature in such a way that the operation would only target the item rather than deleting the entire receipt and adding it back again. 

### Totals that Sum Together

My initial implementation required the user to add up item values by hand. I changed this so that the receipt totals and subtotals would be updated automatically. 

### Monthly Budgets (Feedback from Reviewer)

Instead of just visualizations of the totals, have there be budgets which the user would want to keep to. These budgets will keep a running total of how much has been spent in each category and provide a visualization of how much has been used. 