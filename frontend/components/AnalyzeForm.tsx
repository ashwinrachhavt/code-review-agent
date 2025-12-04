import { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Upload, Code, Send, Folder } from 'lucide-react';
import { Label } from '@/components/ui/label';

interface AnalyzeFormProps {
    onSubmit: (data: { code?: string; files?: File[]; entry?: string; mode: string }) => void;
    isLoading: boolean;
}

export function AnalyzeForm({ onSubmit, isLoading }: AnalyzeFormProps) {
    const [code, setCode] = useState('');
    const [files, setFiles] = useState<File[]>([]);
    const [folderPath, setFolderPath] = useState('');
    const [activeTab, setActiveTab] = useState('paste');

    const handleSubmit = () => {
        if (activeTab === 'paste' && code.trim()) {
            onSubmit({ code, mode: 'orchestrator' });
        } else if (activeTab === 'upload' && files.length > 0) {
            onSubmit({ files, mode: 'orchestrator' });
        } else if (activeTab === 'folder' && folderPath.trim()) {
            onSubmit({ entry: folderPath, mode: 'orchestrator' });
        }
    };

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files) {
            setFiles(Array.from(e.target.files));
        }
    };

    const removeFile = (index: number) => {
        setFiles(files.filter((_, i) => i !== index));
    };

    return (
        <div className="space-y-4">
            <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                <TabsList className="grid w-full grid-cols-3">
                    <TabsTrigger value="paste">
                        <Code className="w-4 h-4 mr-2" />
                        Paste
                    </TabsTrigger>
                    <TabsTrigger value="upload">
                        <Upload className="w-4 h-4 mr-2" />
                        Upload
                    </TabsTrigger>
                    <TabsTrigger value="folder">
                        <Folder className="w-4 h-4 mr-2" />
                        Folder
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="paste" className="space-y-4 mt-4">
                    <div className="space-y-2">
                        <Label htmlFor="code">Paste your code here</Label>
                        <Textarea
                            id="code"
                            placeholder="def fibonacci(n):&#10;    if n <= 1:&#10;        return n&#10;    return fibonacci(n-1) + fibonacci(n-2)"
                            value={code}
                            onChange={(e) => setCode(e.target.value)}
                            className="min-h-[300px] font-mono text-sm"
                            disabled={isLoading}
                        />
                    </div>
                    <Button
                        onClick={handleSubmit}
                        disabled={!code.trim() || isLoading}
                        className="w-full"
                        size="lg"
                    >
                        <Send className="w-4 h-4 mr-2" />
                        {isLoading ? 'Analyzing...' : 'Analyze Code'}
                    </Button>
                </TabsContent>

                <TabsContent value="upload" className="space-y-4 mt-4">
                    <div className="space-y-2">
                        <Label htmlFor="files">Select files to analyze</Label>
                        <div className="border-2 border-dashed rounded-lg p-8 text-center hover:border-primary/50 transition-colors">
                            <input
                                id="files"
                                type="file"
                                multiple
                                accept=".py,.js,.ts,.tsx,.jsx,.java"
                                onChange={handleFileChange}
                                className="hidden"
                                disabled={isLoading}
                            />
                            <label
                                htmlFor="files"
                                className="cursor-pointer flex flex-col items-center gap-2"
                            >
                                <Upload className="w-8 h-8 text-muted-foreground" />
                                <div className="text-sm text-muted-foreground">
                                    Click to select files or drag and drop
                                </div>
                                <div className="text-xs text-muted-foreground">
                                    Supports: .py, .js, .ts, .tsx, .jsx, .java
                                </div>
                            </label>
                        </div>

                        {files.length > 0 && (
                            <div className="space-y-2 mt-4">
                                <Label>Selected files ({files.length})</Label>
                                <div className="border rounded-lg divide-y max-h-[200px] overflow-y-auto">
                                    {files.map((file, index) => (
                                        <div
                                            key={index}
                                            className="flex items-center justify-between p-2 hover:bg-muted/50"
                                        >
                                            <span className="text-sm truncate flex-1">{file.name}</span>
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                onClick={() => removeFile(index)}
                                                disabled={isLoading}
                                            >
                                                Remove
                                            </Button>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>

                    <Button
                        onClick={handleSubmit}
                        disabled={files.length === 0 || isLoading}
                        className="w-full"
                        size="lg"
                    >
                        <Send className="w-4 h-4 mr-2" />
                        {isLoading ? 'Analyzing...' : `Analyze ${files.length} File${files.length !== 1 ? 's' : ''}`}
                    </Button>
                </TabsContent>

                <TabsContent value="folder" className="space-y-4 mt-4">
                    <div className="space-y-2">
                        <Label htmlFor="folder">Server-side Folder Path</Label>
                        <Input
                            id="folder"
                            placeholder="/path/to/your/project"
                            value={folderPath}
                            onChange={(e) => setFolderPath(e.target.value)}
                            disabled={isLoading}
                        />
                        <p className="text-xs text-muted-foreground">
                            Enter the absolute path to a folder on the server to scan.
                        </p>
                    </div>
                    <Button
                        onClick={handleSubmit}
                        disabled={!folderPath.trim() || isLoading}
                        className="w-full"
                        size="lg"
                    >
                        <Send className="w-4 h-4 mr-2" />
                        {isLoading ? 'Analyzing...' : 'Scan Folder'}
                    </Button>
                </TabsContent>
            </Tabs>
        </div>
    );
}
