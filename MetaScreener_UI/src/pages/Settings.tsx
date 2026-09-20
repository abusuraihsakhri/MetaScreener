

export default function Settings() {
  return (
    <div className="p-8 max-w-3xl mx-auto space-y-8 animate-in fade-in duration-500">
      <header className="space-y-1">
        <h1 className="text-3xl font-semibold tracking-tight text-gray-900">Settings</h1>
        <p className="text-gray-500 text-sm">Configure AI providers, thresholds, and application preferences.</p>
      </header>

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
        <div className="p-6 border-b border-gray-100">
          <h2 className="text-lg font-semibold text-gray-900">AI Provider Configuration</h2>
          <p className="text-sm text-gray-500 mt-1">Set your active AI model for automated screening.</p>
        </div>
        
        <div className="p-6 space-y-6">
          <div className="space-y-3">
            <label className="block text-sm font-medium text-gray-700">Active Provider</label>
            <div className="grid grid-cols-3 gap-3">
              {['Ollama (Local)', 'OpenAI', 'Anthropic'].map((provider, i) => (
                <label key={i} className={`flex items-center justify-center px-4 py-3 border rounded-lg cursor-pointer transition-all ${i === 0 ? 'border-primary bg-primary/5 text-primary font-semibold ring-1 ring-primary' : 'border-gray-200 text-gray-700 hover:bg-gray-50'}`}>
                  <input type="radio" name="provider" className="sr-only" defaultChecked={i === 0} />
                  <span className="text-sm">{provider}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="block text-sm font-medium text-gray-700">Ollama API URL</label>
            <input 
              type="url" 
              defaultValue="http://localhost:11434" 
              className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all"
            />
          </div>

          <div className="space-y-1.5">
            <label className="block text-sm font-medium text-gray-700">Ollama Model</label>
            <input 
              type="text" 
              defaultValue="mistral" 
              className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all"
            />
          </div>
        </div>
        <div className="p-4 bg-gray-50 border-t border-gray-100 flex justify-end">
          <button className="px-5 py-2 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary-hover shadow-sm transition-colors">
            Save Settings
          </button>
        </div>
      </div>
    </div>
  );
}
