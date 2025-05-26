# Test Suite

This directory contains all test files for the IMX296 camera capture system.

## Test Files

### `test_simple_integration.py`
- **Purpose**: Basic integration test to verify all modules can be imported and basic functionality works
- **Tests**: 5 tests covering imports, configuration, ntfy handler, video recorder, and GScrop script
- **Usage**: Quick verification that the system is properly set up

### `test_integrated_system.py`
- **Purpose**: Comprehensive test suite with mocking for full system testing
- **Tests**: 12 tests covering all system components and integration scenarios
- **Features**: Mock-based testing, performance testing, system integration flows

### `test_gscrop_integration.py`
- **Purpose**: Specific tests for GScrop script integration and file structure validation
- **Tests**: 4 tests covering directory structure, configuration, GScrop script, and launcher
- **Features**: File system validation, script permissions, content verification

## Running Tests

```bash
# Run all tests from project root
/path/to/conda/envs/dog_track/bin/python tests/test_simple_integration.py
/path/to/conda/envs/dog_track/bin/python tests/test_integrated_system.py
/path/to/conda/envs/dog_track/bin/python tests/test_gscrop_integration.py
```

## Test Status
- ✅ **All tests passing**: 21/21 tests
- ✅ **Coverage**: Complete system coverage with mocking
- ✅ **Performance**: Frame queue performance validation included 