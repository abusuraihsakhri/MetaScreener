

export default function Screening() {
  return (
    <div className="p-8 max-w-4xl mx-auto space-y-6 animate-in fade-in duration-500">
      <header className="flex justify-between items-end">
        <div className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight text-gray-900">Title & Abstract Screening</h1>
          <p className="text-gray-500 text-sm">Paper 45 of 906 (Pending)</p>
        </div>
        <div className="flex gap-2">
          <button className="px-3 py-1.5 bg-primary/10 text-primary rounded-lg text-sm font-medium hover:bg-primary/20 transition-colors flex items-center gap-2">
            ✨ AI Screen
          </button>
        </div>
      </header>

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden flex flex-col">
        {/* Paper Content */}
        <div className="p-6 md:p-8 space-y-6">
          <div>
            <h2 className="text-xl font-bold text-gray-900 leading-snug">
              Machine Learning Applications in Systematic Reviews: A Comprehensive Meta-Analysis of Current Methodologies
            </h2>
            <p className="text-sm text-gray-500 mt-2">
              Authors: Smith, J., Johnson, M. | Year: 2024 | DOI: 10.1234/example.2024
            </p>
          </div>
          
          <div className="prose prose-sm max-w-none text-gray-700">
            <h3 className="text-sm font-semibold text-gray-900 uppercase tracking-wider mb-2">Abstract</h3>
            <p className="leading-relaxed">
              Background: The exponential growth of scientific literature has made systematic reviews increasingly resource-intensive. Machine learning (ML) techniques offer potential solutions for automating various stages of the review process. 
              <br/><br/>
              Methods: We conducted a comprehensive meta-analysis of 142 studies utilizing ML for title/abstract screening, full-text screening, and data extraction. 
              <br/><br/>
              Results: Active learning classifiers demonstrated a 40% reduction in screening workload while maintaining 98% recall. Large Language Models (LLMs) showed promise in complex data extraction tasks.
              <br/><br/>
              Conclusion: ML methodologies significantly reduce systematic review workload, though human-in-the-loop validation remains essential for critical health-related reviews.
            </p>
          </div>
        </div>

        {/* Action Bar */}
        <div className="bg-gray-50 border-t border-gray-200 p-4 sm:px-8 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="w-full sm:w-1/2">
            <input 
              type="text" 
              placeholder="Add exclusion reason (optional)..." 
              className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
          <div className="flex gap-2 w-full sm:w-auto">
            <button className="flex-1 sm:flex-none px-6 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-100 transition-colors shadow-sm">
              Skip
            </button>
            <button className="flex-1 sm:flex-none px-6 py-2 bg-red-600 border border-transparent text-white rounded-lg text-sm font-medium hover:bg-red-700 transition-colors shadow-sm">
              Exclude
            </button>
            <button className="flex-1 sm:flex-none px-6 py-2 bg-emerald-600 border border-transparent text-white rounded-lg text-sm font-medium hover:bg-emerald-700 transition-colors shadow-sm">
              Include
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
