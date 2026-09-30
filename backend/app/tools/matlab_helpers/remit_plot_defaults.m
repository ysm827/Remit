function remit_plot_defaults
% Select an installed CJK font instead of MATLAB's Latin-only default.
available = listfonts;
preferred = {'Microsoft YaHei','SimHei','PingFang SC','Heiti SC','Noto Sans CJK SC','Noto Sans SC','FandolHei'};
for i = 1:numel(preferred)
    if any(strcmpi(available, preferred{i}))
        set(groot, 'defaultAxesFontName', preferred{i}, ...
            'defaultTextFontName', preferred{i}, ...
            'defaultLegendFontName', preferred{i});
        return
    end
end
warning('Remit:MissingCJKFont', '未找到中文绘图字体，请安装 Noto Sans CJK；中文图表需检查后才能用于论文。');
end
