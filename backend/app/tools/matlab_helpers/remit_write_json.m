function saved = remit_write_json(filename, payload, requiredFields)
% Validate, UTF-8 encode, read back, then atomically replace a result file.
% This checks structure only. It never creates or changes scientific metrics.
if nargin < 3, requiredFields = strings(0, 1); end
filename = char(filename);
[folder, stem, ext] = fileparts(filename);
if ~isempty(folder) || isempty(stem) || startsWith(stem, '.') || ~strcmpi(ext, '.json')
    error('Remit:Path', 'Use a plain result filename ending in .json');
end
reserved = ["workflow_state.json", "execution_backend.json", "problem.json"];
if any(strcmpi(filename, reserved))
    error('Remit:Path', 'Cannot overwrite application state');
end
if isfile('.remit-inputs.json')
    inputs = string(jsondecode(fileread('.remit-inputs.json')));
    if any(strcmpi(filename, inputs))
        error('Remit:Path', 'Cannot overwrite an input attachment');
    end
end
errors = strings(0, 1);
if ~isstruct(payload) || ~isscalar(payload)
    errors(end+1) = "Result must be a scalar struct";
else
    for field = reshape(string(requiredFields), 1, [])
        if ~isfield(payload, field), errors(end+1) = "Missing field: " + field; end
    end
    if startsWith(filename, 'pilot_')
        errors = [errors; pilot_errors(payload)];
    end
end
if ~isempty(errors)
    error('Remit:Schema', '%s', strjoin(errors, newline));
end
if startsWith(filename, 'pilot_')
    for key = string(fieldnames(payload.questions))'
        if isstruct(payload.questions.(key).candidates)
            payload.questions.(key).candidates = num2cell(payload.questions.(key).candidates);
        end
    end
end
encoded = jsonencode(payload);
saved = jsondecode(encoded);
temp = [tempname(pwd), '.json'];
cleanup = onCleanup(@() remove_temp(temp));
fid = fopen(temp, 'w', 'n', 'UTF-8');
if fid < 0, error('Remit:Write', 'Cannot open temporary result'); end
try
    count = fwrite(fid, unicode2native(encoded, 'UTF-8'), 'uint8');
    closeStatus = fclose(fid);
catch exc
    fclose(fid);
    rethrow(exc);
end
if closeStatus ~= 0 || count ~= numel(unicode2native(encoded, 'UTF-8'))
    error('Remit:Write', 'Result write was incomplete');
end
decoded = jsondecode(fileread(temp));
if ~isequaln(decoded, saved), error('Remit:Write', 'Result readback mismatch'); end
options = javaArray('java.nio.file.CopyOption', 2);
options(1) = java.nio.file.StandardCopyOption.ATOMIC_MOVE;
options(2) = java.nio.file.StandardCopyOption.REPLACE_EXISTING;
java.nio.file.Files.move(java.io.File(temp).toPath(), ...
    java.io.File(fullfile(pwd, filename)).toPath(), options);
end

function errors = pilot_errors(payload)
errors = strings(0, 1);
if ~isfield(payload, 'questions') || ~isstruct(payload.questions) || ~isscalar(payload.questions)
    errors(end+1) = "questions must be a scalar struct";
    return
end
for key = string(fieldnames(payload.questions))'
    entry = payload.questions.(key);
    if ~isstruct(entry) || ~isscalar(entry)
        errors(end+1) = key + " must be a scalar struct";
        continue
    end
    if ~isfield(entry, 'sample_description') || ~is_text(entry.sample_description)
        errors(end+1) = key + ".sample_description must be nonempty text";
    end
    if ~isfield(entry, 'candidates') || isempty(entry.candidates)
        errors(end+1) = key + ".candidates is missing or empty";
        continue
    end
    candidates = entry.candidates;
    if isstruct(candidates), candidates = num2cell(candidates); end
    if ~iscell(candidates)
        errors(end+1) = key + ".candidates must contain structs";
        continue
    end
    for i = 1:numel(candidates)
        candidate = candidates{i};
        prefix = key + ".candidates[" + i + "]";
        if ~isstruct(candidate) || ~isscalar(candidate)
            errors(end+1) = prefix + " must be a scalar struct";
            continue
        end
        for field = ["name", "metric_name", "notes"]
            if ~isfield(candidate, field) || ~is_text(candidate.(field))
                errors(end+1) = prefix + "." + field + " must be nonempty text";
            end
        end
        if ~isfield(candidate, 'ran_ok') || ~islogical(candidate.ran_ok) || ~isscalar(candidate.ran_ok)
            errors(end+1) = prefix + ".ran_ok must be a logical scalar";
            continue
        end
        for field = ["metric_value", "runtime_seconds"]
            if ~isfield(candidate, field)
                errors(end+1) = prefix + "." + field + " is missing";
                continue
            end
            value = candidate.(field);
            valid = isnumeric(value) && isreal(value) && isscalar(value) && isfinite(value);
            if field == "runtime_seconds" && valid, valid = value >= 0; end
            if ~valid && (candidate.ran_ok || ~isempty(value))
                errors(end+1) = prefix + "." + field + " must be a finite number (or [] for failure)";
            end
        end
    end
end
end

function result = is_text(value)
result = (ischar(value) && isrow(value) && ~isempty(strtrim(value))) || ...
    (isstring(value) && isscalar(value) && ~ismissing(value) && strlength(strtrim(value)) > 0);
end

function remove_temp(path)
if isfile(path), delete(path); end
end
