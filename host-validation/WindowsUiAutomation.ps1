# Internal owned-window helpers; Windows PowerShell 5, UTF-8 BOM required.
$ErrorActionPreference = 'Stop'
Add-Type -Path "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\WPF\UIAutomationClient.dll"
Add-Type -Path "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\WPF\UIAutomationTypes.dll"
Add-Type -ReferencedAssemblies @("System.dll", "System.Core.dll", "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\WPF\UIAutomationClient.dll", "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\WPF\UIAutomationTypes.dll") @"
using System;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Automation;

public static class OwnWindow {
    public delegate bool EnumProc(IntPtr handle, IntPtr parameter);
    [DllImport("user32.dll")]
    static extern bool EnumWindows(EnumProc callback, IntPtr parameter);
    [DllImport("user32.dll")]
    static extern uint GetWindowThreadProcessId(IntPtr handle, out uint processId);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)]
    static extern int GetWindowText(IntPtr handle, StringBuilder text, int count);
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr handle, int command);
    [DllImport("user32.dll")]
    public static extern bool PostMessage(IntPtr handle, uint message, IntPtr w, IntPtr l);

    [StructLayout(LayoutKind.Sequential)] public struct Point { public int x; public int y; }
    [DllImport("user32.dll")] static extern bool ScreenToClient(IntPtr h, ref Point p);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr parent, EnumProc cb, IntPtr l);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder text, int count);
    [DllImport("user32.dll")] static extern int GetDlgCtrlID(IntPtr h);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)]
    static extern IntPtr SendMessageTimeout(IntPtr h, uint message, IntPtr w, string l, uint flags, uint timeout, out IntPtr result);

    public static void Click(IntPtr h, double x, double y) {
        var p = new Point{x=(int)x,y=(int)y};
        if (!ScreenToClient(h, ref p)) throw new Exception("Coordinate conversion failed");
        var position = new IntPtr((p.y<<16)|(p.x&65535));
        if (!PostMessage(h,0x201,new IntPtr(1),position) || !PostMessage(h,0x202,IntPtr.Zero,position))
            throw new Exception("Owned mouse message failed");
    }
    public static IntPtr FindClass(int processId, string className, string title) {
        IntPtr result=IntPtr.Zero; int count=0;
        EnumWindows((h,l)=>{
            uint owner; GetWindowThreadProcessId(h,out owner);
            if (owner==processId && IsWindowVisible(h)) {
                var cls=new StringBuilder(256); var text=new StringBuilder(256);
                GetClassName(h,cls,256); GetWindowText(h,text,256);
                string exposedClass=cls.ToString();
                if(className.StartsWith("Q")) exposedClass=AutomationElement.FromHandle(h).Current.ClassName;
                if(exposedClass==className && (string.IsNullOrEmpty(title) || text.ToString()==title)) {result=h;count++;}
            }
            return true;
        },IntPtr.Zero);
        if(count>1) throw new Exception("Owned window class/title was not unique");
        return result;
    }
    public static IntPtr Child(IntPtr parent,int processId,int controlId,string className) {
        IntPtr result=IntPtr.Zero; int count=0;
        EnumChildWindows(parent,(h,l)=>{
            uint owner; GetWindowThreadProcessId(h,out owner);
            if(owner==processId && GetDlgCtrlID(h)==controlId) {
                var cls=new StringBuilder(256); GetClassName(h,cls,256);
                if(cls.ToString()==className) {result=h;count++;}
            }
            return true;
        },IntPtr.Zero);
        if(count!=1) throw new Exception("Native child was not unique: "+className+"/"+controlId);
        return result;
    }
    public static void SetText(IntPtr h,string text) {
        IntPtr result;
        if(SendMessageTimeout(h,0xC,IntPtr.Zero,text,2,2000,out result)==IntPtr.Zero || result==IntPtr.Zero)
            throw new Exception("Native filename could not be set");
    }
    // Modal Invoke can block until the dialog closes; use a separate task.
    public static Task InvokeAsync(AutomationElement element) {
        return Task.Run(() => ((InvokePattern)element.GetCurrentPattern(InvokePattern.Pattern)).Invoke());
    }
    public static IntPtr Find(int processId) {
        return Find(processId, "Audio Transcriber — Lecture library");
    }
    public static IntPtr Find(int processId, string title) {
        IntPtr result = IntPtr.Zero;
        EnumWindows((handle, parameter) => {
            uint owner;
            GetWindowThreadProcessId(handle, out owner);
            if (owner == processId) {
                var text = new StringBuilder(256);
                GetWindowText(handle, text, text.Capacity);
                if (text.ToString() == title) result = handle;
            }
            return true;
        }, IntPtr.Zero);
        return result;
    }
}
"@

# Inspect only windows belonging to the process launched below. Never use the desktop root.
function FindControl($Root, [string]$Name, $Type) {
    $condition=[System.Windows.Automation.AndCondition]::new(
        [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::NameProperty,$Name),
        [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty,$Type))
    $found=$Root.FindAll([System.Windows.Automation.TreeScope]::Descendants,$condition)
    if($found.Count -ne 1) { throw "Expected one owned control: $Name; got $($found.Count)" }
    return $found[0]
}
function ValueOf($Element) {
    return [System.Windows.Automation.ValuePattern]$Element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
}
function InvokeControl($Element) {
    $task=[OwnWindow]::InvokeAsync($Element)
    if(-not $task.Wait(5000)) { throw 'Owned control invocation timed out' }
}
function WaitWindow([int]$ProcessId,[string]$Title) {
    $deadline=(Get-Date).AddSeconds(30)
    do {
        $handle=[OwnWindow]::Find($ProcessId,$Title)
        if($handle -ne [IntPtr]::Zero) {
            [OwnWindow]::ShowWindow($handle,0) | Out-Null
            Start-Sleep -Milliseconds 200
            return [System.Windows.Automation.AutomationElement]::FromHandle($handle)
        }
        Start-Sleep -Milliseconds 100
    } while((Get-Date) -lt $deadline)
    throw "Owned window did not appear: $Title"
}

function WaitUntil([scriptblock]$Condition,[string]$Failure,[int]$Seconds=10) {
    $deadline=(Get-Date).AddSeconds($Seconds)
    while(-not (& $Condition)) {
        if((Get-Date) -ge $deadline) { throw $Failure }
        Start-Sleep -Milliseconds 100
    }
}
function ClickElement([IntPtr]$Handle,$Element) {
    $rect=$Element.Current.BoundingRectangle
    if($rect.Width -le 0 -or $rect.Height -le 0) { throw 'Owned control has no click rectangle' }
    [OwnWindow]::Click($Handle,($rect.Left+$rect.Width/2),($rect.Top+$rect.Height/2))
}
function SelectCombo([int]$ProcessId,[IntPtr]$Handle,$Root,[string]$Name,[string]$Value) {
    $combo=FindControl $Root $Name ([System.Windows.Automation.ControlType]::ComboBox)
    if((ValueOf $combo).Current.Value -eq $Value) { return }
    ClickElement $Handle $combo
    WaitUntil { [OwnWindow]::FindClass($ProcessId,'QComboBoxPrivateContainer',$null) -ne [IntPtr]::Zero } 'Owned dropdown did not open'
    $popup=[OwnWindow]::FindClass($ProcessId,'QComboBoxPrivateContainer',$null)
    $root=[System.Windows.Automation.AutomationElement]::FromHandle($popup)
    ClickElement $popup (FindControl $root $Value ([System.Windows.Automation.ControlType]::ListItem))
    WaitUntil { (ValueOf $combo).Current.Value -eq $Value } 'Dropdown did not select the requested value'
}
function FilePicker([int]$ProcessId,[string]$Title,[string]$Path,[int]$FilenameId=1001) {
    # Qt also owns an empty QFileDialog wrapper with the same title. Use #32770.
    WaitUntil { [OwnWindow]::FindClass($ProcessId,'#32770',$Title) -ne [IntPtr]::Zero } 'Owned Windows file picker absent'
    $dialog=[OwnWindow]::FindClass($ProcessId,'#32770',$Title)
    WaitUntil { try { [OwnWindow]::Child($dialog,$ProcessId,$FilenameId,'Edit') | Out-Null; return $true } catch { return $false } } 'Windows filename control did not become ready'
    [OwnWindow]::SetText([OwnWindow]::Child($dialog,$ProcessId,$FilenameId,'Edit'),[IO.Path]::GetFullPath($Path))
    [OwnWindow]::PostMessage([OwnWindow]::Child($dialog,$ProcessId,1,'Button'),0xF5,[IntPtr]::Zero,[IntPtr]::Zero) | Out-Null
    WaitUntil { [OwnWindow]::FindClass($ProcessId,'#32770',$Title) -eq [IntPtr]::Zero } 'Windows file picker remained open'
}

