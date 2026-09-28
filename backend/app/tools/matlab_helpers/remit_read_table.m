function [T, profile] = remit_read_table(filename, textColumns)
% Read a table without renaming headers or mixing cellstr/string columns.
% Declare identifiers explicitly, e.g. remit_read_table('x.csv', ["编号"]).
% Missing values stay missing; no imputation or scientific conversion occurs.
if nargin < 2, textColumns = strings(0, 1); end
opts = detectImportOptions(filename, 'VariableNamingRule', 'preserve');
names = string(opts.VariableNames);
unknown = setdiff(string(textColumns), names);
if ~isempty(unknown)
    error('Remit:Columns', 'Unknown text columns: %s', strjoin(unknown, ', '));
end
if ~isempty(textColumns)
    opts = setvartype(opts, cellstr(textColumns), 'string');
end
T = readtable(filename, opts);
profile = struct('rows', height(T), 'columns', []);
columns = cell(1, width(T));
for i = 1:width(T)
    name = T.Properties.VariableNames{i};
    value = T.(name);
    if iscellstr(value) || ischar(value)
        value = string(value);
        value(strlength(value) == 0) = missing;
        T.(name) = value;
    end
    columns{i} = struct('name', name, 'type', class(value), ...
        'missing_count', sum(ismissing(value), 'all'));
end
profile.columns = columns;
end
