function values = remit_numeric_column(T, name)
% Explicit conversion only; preserve missing as NaN and reject other bad text.
raw = T.(name);
if isnumeric(raw)
    values = double(raw);
    return
end
text = string(raw);
missingRows = ismissing(text) | strlength(strtrim(text)) == 0;
values = str2double(text);
bad = ~missingRows & isnan(values);
if any(bad, 'all')
    rows = find(bad);
    error('Remit:NumericColumn', 'Column %s has nonnumeric values at rows %s', ...
        char(name), char(strjoin(string(rows(1:min(10, numel(rows)))), ', ')));
end
values(missingRows) = NaN;
end
